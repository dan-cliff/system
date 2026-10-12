/** @odoo-module **/

import { registry } from "@web/core/registry";
import { aiProgress } from "@social_manager/ai_progress/ai_progress";

/**
 * Runs a Social Manager AI job behind the progress overlay.
 *
 * The server returns this client action from the AI buttons (the button saves the
 * record first), with params {model, ids, method, steps_method, title}. The job:
 *   1. asks the server what it is about to do (steps_method) so the AI step names
 *      what is being generated,
 *   2. calls `method`, which does the AI work and returns {type, message},
 *   3. reloads the view and shows the result as a notification.
 */
async function socialManagerAiJob(env, action) {
    const { model, ids, method, steps_method, title } = action.params;
    const orm = env.services.orm;
    const notification = env.services.notification;
    if (aiProgress.active) {
        return;
    }
    // Record buttons save the record before the job starts; list buttons have nothing to save.
    const before = ids.length ? ["Saving", "Checking what is needed"] : ["Checking what is needed"];
    aiProgress.start(title, [...before, "Asking the AI", "Updating the records"]);
    if (ids.length) {
        aiProgress.next();
    }
    try {
        const steps = await orm.call(model, steps_method, [ids, method]);
        aiProgress.setSteps([...before, ...steps]);
        aiProgress.next();
        // Steps from the server: [preparing, asking the AI, updating]; the AI call covers the
        // first two, so move to the AI step before waiting on it.
        if (steps.length > 2) {
            aiProgress.next();
        }
        const result = (await orm.call(model, method, [ids])) || {};
        aiProgress.next();
        notification.add(result.message || "Done.", { type: result.type || "success" });
    } catch (error) {
        aiProgress.fail();
        const message =
            (error && error.data && error.data.message) ||
            (error && error.message) ||
            "Something went wrong while the AI was working.";
        notification.add(message, { type: "danger", sticky: true });
    } finally {
        aiProgress.stop();
    }
    return { type: "ir.actions.client", tag: "soft_reload" };
}

registry.category("actions").add("social_manager_ai_job", socialManagerAiJob);
