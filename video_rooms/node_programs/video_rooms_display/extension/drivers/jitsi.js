// Video Rooms - Jitsi Meet driver (SCAFFOLD). No DOM scraping: runs in the Display's own
// page and controls Jitsi through its official External API (JitsiMeetExternalAPI in an
// iframe): executeCommand('toggleAudio'), events such as 'audioMuteStatusChanged', ...
// Works for meet.jit.si and self-hosted servers. See DESIGN.md §3.
class JitsiDriver extends VideoRoomsDriver {
    static platform = "jitsi";
}
