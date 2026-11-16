// Video Rooms - the interface every platform driver implements (SCAFFOLD).
// Drivers run as content scripts inside the platform's web client and act on it the
// way a person would (buttons, keyboard shortcuts). Selectors live in selectors.json
// so a vendor UI change is a data fix released over the air.
/* eslint-disable no-unused-vars */
class VideoRoomsDriver {
    static platform = "generic";
    async join({ url, displayName, email, meetingCode, passcode, mic, camera }) { throw new Error("not built"); }
    async leave() { throw new Error("not built"); }
    async setMic(on) { throw new Error("not built"); }
    async setCamera(on) { throw new Error("not built"); }
    async startShare(windowTitle) { throw new Error("not built"); }
    async stopShare() { throw new Error("not built"); }
    async setLayout(name) { throw new Error("not built"); }
    /** {state: idle|prejoin|lobby|in_call|ended|error, mic, camera, sharing, participants, error} */
    getState() { return { state: "idle" }; }
    /** Checks every selector still matches the current web client. */
    async selfTest() { throw new Error("not built"); }
}
