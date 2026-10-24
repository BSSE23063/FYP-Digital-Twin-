import { useCallback, useRef, useState } from "react";

/** Simple click-to-record / click-to-stop recorder for the chat composer's
 * mic button — deliberately no voice-activity-detection here (that's
 * useVoiceCall's job for the dedicated Call mode). This is the "a person can
 * simply select audio input and add its context as audio" path: press, talk,
 * press again, it's sent. */
export function usePushToTalk(onError?: (message: string) => void) {
  const [isRecording, setIsRecording] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = ["audio/webm;codecs=opus", "audio/webm"].find((t) =>
        MediaRecorder.isTypeSupported(t)
      );
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start();
      recorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) {
      onError?.(
        err instanceof Error ? `Couldn't access the microphone: ${err.message}` : "Couldn't access the microphone."
      );
    }
  }, [onError]);

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = recorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setIsRecording(false);
        if (chunksRef.current.length === 0) {
          resolve(null);
          return;
        }
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      };
      recorder.stop();
    });
  }, []);

  return { isRecording, start, stop };
}
