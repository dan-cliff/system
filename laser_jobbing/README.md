# Laser Jobbing

Personalised laser cutting, scoring and engraving for Odoo 19. A support app:
it has no menu of its own. Jobs are collected and worked through in
**Manufacturing** (`laser_jobbing_manufacturing`), and come from **Sales** and
the **eCommerce** shop (`laser_jobbing_sale`, `laser_jobbing_website_sale`).
These bridges install automatically with their apps.

## Templates

A template is a base design plus **variable elements**:

| Operation | Base file | Artwork elements | Job file |
| --- | --- | --- | --- |
| Cutting | `.svg` | `.svg` | `.svg` |
| Scoring | `.svg` | `.svg` | `.svg` |
| Engraving | png, jpg, jpeg, bmp, webp, tif, tiff, gif, heic | same | the format of the picture uploaded |

Each element is a **text** (font, size, alignment, shrink to fit, character
limit, several lines, colour) or a **picture / artwork** (fit inside or fill
its box), placed in mm from the top left of the design. Elements marked
*Customer Fills In* are offered to customers in the shop; the others keep
their defaults and only employees change them.

## Jobs and their files

Every change to a job makes its laser file again (Download Laser File).

- **Cutting / scoring**: an `.svg` sized in mm. Text becomes outlines (paths)
  when its font has a font file and the `fontTools` Python library is
  installed; otherwise it stays `<text>` in the font's family.
- **Engraving**: a picture at the template's dpi (optionally in greys), saved
  in the format of the picture the customer or employee uploaded, else of the
  element's default picture, else of the template's base picture (PNG when
  there is none). HEIC needs the `pillow-heif` library to be combined with
  text or other artwork; a job that is only one HEIC picture keeps it as is.

Uploaded SVGs are parsed without entities or network access and stripped of
scripts, event handlers and external references before they are shown or
embedded.

## Settings (Settings › Laser Jobbing)

- **Visual Editor for Employees**: drag and resize elements on the template's
  design, and a live preview on jobs.
- **Visual Editor for Customers**: live preview on the eCommerce product page
  while customers type and pick pictures.
- **Upload Limit** (MB), and links to Templates, Fonts, Materials and Jobs.

## Optional Python libraries

- `fontTools`: outlines text in cutting and scoring files.
- `pillow-heif`: reads and writes HEIC pictures.
