/** Wireless share, room side (in the "Video Rooms Share" window on the Room Display):
 *  answer the laptop's WebRTC offer and show its screen. */
window.VideoRoomsShareReceiver = {
    async start(video, msg) {
        const session = new URLSearchParams(location.search).get("session");
        msg.textContent = "Connecting to the laptop…";
        try {
            const offer = await (await fetch(`/video_rooms/node/v1/share/${encodeURIComponent(session)}`, { cache: "no-store" })).json();
            if (!offer.sdp) {
                throw new Error(offer.message || "The share has ended.");
            }
            const pc = new RTCPeerConnection({ iceServers: offer.ice_servers || [] });
            pc.addEventListener("track", (event) => {
                video.srcObject = event.streams[0];
                msg.textContent = "";
            });
            pc.addEventListener("connectionstatechange", () => {
                if (["failed", "disconnected"].includes(pc.connectionState)) {
                    msg.textContent = "The laptop stopped sharing.";
                }
            });
            await pc.setRemoteDescription({ type: "offer", sdp: offer.sdp });
            await pc.setLocalDescription(await pc.createAnswer());
            await new Promise((resolve) => {
                if (pc.iceGatheringState === "complete") {
                    resolve();
                    return;
                }
                pc.addEventListener("icegatheringstatechange", () => pc.iceGatheringState === "complete" && resolve());
                setTimeout(resolve, 4000);
            });
            await fetch(`/video_rooms/node/v1/share/${encodeURIComponent(session)}/answer`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sdp: pc.localDescription.sdp }),
            });
        } catch (error) {
            msg.textContent = `Wireless share: ${error.message}`;
        }
    },
};
