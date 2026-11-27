/** Entry point of the Video Rooms tablet apps (Console, door screen, Room Board). */
const app = document.body.dataset.app;
const modules = { console: "./console.js", presence: "./presence.js", board: "./board.js" };
import(modules[app] || modules.presence).then((module) => module.start()).catch((error) => {
    document.getElementById("boot-msg").textContent = `This app failed to start: ${error.message}`;
});
