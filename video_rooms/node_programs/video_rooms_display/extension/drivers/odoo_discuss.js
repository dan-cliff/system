// Video Rooms - Odoo Discuss driver (SCAFFOLD). Registered at runtime for our own Odoo
// address (chrome.scripting.registerContentScripts), since it differs per installation.
// Joins a channel's call through its invitation link as a guest. See DESIGN.md §3.
class OdooDiscussDriver extends VideoRoomsDriver {
    static platform = "odoo_discuss";
}
