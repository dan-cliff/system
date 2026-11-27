/** Wireless share, laptop side: capture the screen and send it to the room's PC over WebRTC.
 *  Odoo only carries the offer and the answer (no trickle ICE: each side gathers first). */
const $ = (id) => document.getElementById(id);
let pc = null;
let token = null;
let stream = null;

async function rpc(path, params) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }) });
    const data = await response.json();
    if (data.error) {
        throw new Error(data.error.data?.message || data.error.message);
    }
    return data.result;
}

function status(text, cls = "") {
    $("status").textContent = text;
    $("status").className = `status ${cls}`;
}

function gathered(peer) {
    return new Promise((resolve) => {
        if (peer.iceGatheringState === "complete") {
            resolve();
            return;
        }
        peer.addEventListener("icegatheringstatechange", () => peer.iceGatheringState === "complete" && resolve());
        setTimeout(resolve, 4000);
    });
}

async function start(code) {
    if (!navigator.mediaDevices?.getDisplayMedia) {
        status("This browser can't share its screen. Use Chrome, Edge or Firefox on a computer.", "bad");
        return;
    }
    $("go").disabled = true;
    try {
        const begin = await rpc("/video_rooms/share/start", { code });
        if (!begin.ok) {
            throw new Error(begin.message);
        }
        token = begin.token;
        stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 30 } }, audio: false });
        $("preview").srcObject = stream;
        $("preview").hidden = false;
        stream.getVideoTracks()[0].addEventListener("ended", stop);
        pc = new RTCPeerConnection({ iceServers: begin.ice_servers || [] });
        for (const track of stream.getTracks()) {
            pc.addTrack(track, stream);
        }
        await pc.setLocalDescription(await pc.createOffer());
        status(`Connecting to ${begin.room}…`);
        await gathered(pc);
        const offered = await rpc("/video_rooms/share/offer", { token, sdp: pc.localDescription.sdp });
        if (!offered.ok) {
            throw new Error(offered.message);
        }
        for (let i = 0; i < 60; i++) {
            const answer = await rpc("/video_rooms/share/answer", { token });
            if (!answer.ok) {
                throw new Error(answer.message);
            }
            if (answer.sdp) {
                await pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });
                status(`Sharing to ${begin.room}.`, "ok");
                $("stop").hidden = false;
                $("form").hidden = true;
                $("go").hidden = true;
                pc.addEventListener("connectionstatechange", () => {
                    if (["failed", "disconnected", "closed"].includes(pc.connectionState)) {
                        status("The connection to the room dropped. Share again.", "bad");
                    }
                });
                return;
            }
            await new Promise((r) => setTimeout(r, 1000));
        }
        throw new Error("The room didn't answer. Check its screens are on, then try again.");
    } catch (error) {
        status(error.message, "bad");
        cleanup();
    }
}

function cleanup() {
    stream?.getTracks().forEach((t) => t.stop());
    pc?.close();
    pc = null;
    stream = null;
    $("preview").hidden = true;
    $("stop").hidden = true;
    $("form").hidden = false;
    $("go").hidden = false;
    $("go").disabled = false;
}

async function stop() {
    if (token) {
        await rpc("/video_rooms/share/stop", { token }).catch(() => {});
    }
    token = null;
    cleanup();
    status("Stopped sharing.");
}

$("form").addEventListener("submit", (e) => {
    e.preventDefault();
    start($("code").value);
});
$("stop").addEventListener("click", stop);
window.addEventListener("beforeunload", () => {
    if (token) {
        const body = JSON.stringify({ jsonrpc: "2.0", method: "call", params: { token } });
        navigator.sendBeacon?.("/video_rooms/share/stop", new Blob([body], { type: "application/json" }));
    }
});
