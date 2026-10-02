#!/usr/bin/env python3
"""Set a module's menu groups from its access_levels.py.

    python3 tools/apply_menu_groups.py <module> [<module> ...]

For each <menuitem> in the module's XML files:

* opening a window action on an OPERATIONAL model: shown to that model's View Only group;
* opening a window action on a CONFIG or SETTINGS model: shown to that model's Create,
  Update and Delete groups (Administrator level), since everyone can read CONFIG models;
* folder menus (no action): groups removed - Odoo hides a folder with no visible children.

Menus opening anything else are listed for review and left unchanged.
"""
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MENU_RE = re.compile(r'<menuitem\b[^>]*?/?>', re.S)
ATTR_RE = r'\b%s\s*=\s*"([^"]*)"'
ACTION_RE = re.compile(
    r'<record\s+id="([^"]+)"\s+model="ir\.actions\.act_window"\s*>(.*?)</record>', re.S)
RES_MODEL_RE = re.compile(r'<field\s+name="res_model"\s*>\s*([\w.]+)\s*</field>')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def xml_files(path):
    for folder, _dirs, files in os.walk(path):
        for name in files:
            if name.endswith('.xml'):
                yield os.path.join(folder, name)


def attr(tag, name):
    match = re.search(ATTR_RE % name, tag)
    return match.group(1) if match else None


def set_groups(tag, groups):
    tag = re.sub(r'\s*\bgroups\s*=\s*"[^"]*"', '', tag)
    if not groups:
        return tag
    end = '/>' if tag.endswith('/>') else '>'
    body = tag[:-len(end)].rstrip()
    indent = re.search(r'\n(\s*)\S', tag)
    sep = '\n' + indent.group(1) if indent else ' '
    return '%s%sgroups="%s"%s' % (body, sep, groups, end)


def main(modules):
    for module in modules:
        path = os.path.join(ROOT, module)
        spec = _load(os.path.join(path, 'access_levels.py'), '%s_access_levels' % module)
        by_model = {}
        for model in spec.MODELS:
            xmlids = model[3].keys() if isinstance(model[3], dict) else model[3]
            for xmlid in xmlids:
                by_model[xmlid.split('.')[-1][len('model_'):].replace('_', '.')] = model
        actions = {}
        for filename in xml_files(path):
            with open(filename) as handle:
                for action_id, body in ACTION_RE.findall(handle.read()):
                    res_model = RES_MODEL_RE.search(body)
                    if res_model:
                        actions[action_id] = res_model.group(1)
        for filename in xml_files(path):
            with open(filename) as handle:
                content = handle.read()

            def replace(match):
                tag = match.group(0)
                action = attr(tag, 'action')
                if not action:
                    return set_groups(tag, None)
                res_model = actions.get(action.split('.')[-1] if action.startswith(module + '.') else action)
                model = by_model.get(res_model.replace('_', '.')) if res_model else None
                if not model:
                    print('%s: review menu %s (action %s, model %s)' % (
                        os.path.relpath(filename, ROOT), attr(tag, 'id'), action, res_model))
                    return tag
                key, kind = model[0], model[2]
                permissions = ('view',) if kind == 'operational' else ('create', 'update', 'delete')
                return set_groups(tag, ','.join(
                    '%s.group_%s_%s_%s' % (module, spec.PREFIX, key, permission)
                    for permission in permissions))

            new_content = MENU_RE.sub(replace, content)
            if new_content != content:
                with open(filename, 'w') as handle:
                    handle.write(new_content)


if __name__ == '__main__':
    main(sys.argv[1:])
