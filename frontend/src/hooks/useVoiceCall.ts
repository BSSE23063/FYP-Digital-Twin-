import { useCallback, useRef, useState } from "react";

export type CallStatus = "idle" | "listening" | "thinking" | "speaking" | "error";

// Tuned by feel, not measured against real speech samples — the honest ceiling
// here is a push-to-talk loop with automatic turn-taking, not a true duplex
// call: backend TTS measures 0.3-0.9x realtime (CLAUDE.md §9.3/§9.5), so every
// turn has a real multi-second pause no frontend tuning can remove. These
// constants only affect how eagerly a pause in speech is treated as "done talking".
const SPEECH_RMS_THRESHOLD = 0.02;
const SILENCE_MS_TO_STOP = 1200;
const MIN_UTTERANCE_MS = 400;
const MAX_UTTERANCE_MS = 60_000;

// Barge-in (session 23): while the twin's reply is playing, the mic is still
// watched so the visitor can interrupt by just talking instead of waiting the
// reply out. Its threshold is intentionally higher than SPEECH_RMS_THRESHOLD
// and requires a sustained run, not one loud frame — the twin's own audio can
// leak into the mic even with echo cancellation on, and a false trigger would
// cut the twin off mid-sentence for nothing.
const BARGE_IN_RMS_THRESHOLD = 0.035;
const BARGE_IN_SUSTAIN_MS = 220;
// Ignores the first moment of playback, before the browser's echo
// cancellation has had any audio to adapt against.
const BARGE_IN_GRACE_MS = 400;

interface UseVoiceCallOptions {
  /** Called with a recorded utterance; must resolve to base64 WAV audio to play back. */
  onUtterance: (blob: Blob) => Promise<string>;
  onError?: (message: string) => void;
}

export function useVoiceCall({ onUtterance, onError }: UseVoiceCallOptions) {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [volume, setVolume] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const rafRef = useRef<number | null>(null);
  const hasSpokenRef = useRef(false);
  const silenceStartRef = useRef<number | null>(null);
  const utteranceStartRef = useRef<number>(0);
  const activeRef = useRef(false);
  const playerRef = useRef<HTMLAudioElement | null>(null);
  const bargeInStartRef = useRef<number | null>(null);

  const stopMonitorLoop = () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  };

  const computeRms = (analyser: AnalyserNode) => {
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);
    let sumSquares = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sumSquares += v * v;
    }
    return Math.sqrt(sumSquares / data.length);
  };

  const pickMimeType = () => {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
    return candidates.find((t) => MediaRecorder.isTypeSupported(t));
  };

  const startListening = useCallback(() => {
    if (!streamRef.current || !activeRef.current) return;
    chunksRef.current = [];
    hasSpokenRef.current = false;
    silenceStartRef.current = null;
    utteranceStartRef.current = performance.now();

    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.start();
    recorderRef.current = recorder;
    setStatus("listening");

    const monitor = () => {
      const analyser = analyserRef.current;
      if (!analyser || !activeRef.current) return;
      const rms = computeRms(analyser);
      setVolume(rms);

      const now = performance.now();
      const utteranceDuration = now - utteranceStartRef.current;

      if (rms > SPEECH_RMS_THRESHOLD) {
        hasSpokenRef.current = true;
        silenceStartRef.current = null;
      } else if (hasSpokenRef.current) {
        if (silenceStartRef.current === null) silenceStartRef.current = now;
        const silenceDuration = now - silenceStartRef.current;
        if (silenceDuration > SILENCE_MS_TO_STOP && utteranceDuration > MIN_UTTERANCE_MS) {
          finishUtterance();
          return;
        }
      }
      if (utteranceDuration > MAX_UTTERANCE_MS) {
        finishUtterance();
        return;
      }
      rafRef.current = requestAnimationFrame(monitor);
    };
    rafRef.current = requestAnimationFrame(monitor);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const finishUtterance = useCallback(() => {
    stopMonitorLoop();
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;

    recorder.onstop = async () => {
      if (!activeRef.current) return;
      if (!hasSpokenRef.current || chunksRef.current.length === 0) {
        // Nothing was actually said (e.g. max-duration safety trip on silence) — just keep listening.
        startListening();
        return;
      }
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      setStatus("thinking");
      try {
        const replyBase64 = await onUtterance(blob);
        if (!activeRef.current) return;
        setStatus("speaking");
        const audio = new Audio(`data:audio/wav;base64,${replyBase64}`);
        playerRef.current = audio;
        const speakingStartedAt = performance.now();
        let interrupted = false;

        // Stops the twin mid-reply and starts listening immediately, instead
        // of waiting for onended — the actual barge-in behavior being added.
        const interruptAndListen = () => {
          if (interrupted) return;
          interrupted = true;
          stopMonitorLoop();
          audio.onended = null;
          audio.onerror = null;
          audio.pause();
          if (activeRef.current) startListening();
        };

        audio.onended = () => {
          stopMonitorLoop();
          if (activeRef.current) startListening();
        };
        audio.onerror = () => {
          stopMonitorLoop();
          if (activeRef.current) startListening();
        };

        bargeInStartRef.current = null;
        const watchForBargeIn = () => {
          const analyser = analyserRef.current;
          if (!analyser || !activeRef.current || interrupted) return;
          const rms = computeRms(analyser);
          setVolume(rms);

          const elapsed = performance.now() - speakingStartedAt;
          if (elapsed > BARGE_IN_GRACE_MS && rms > BARGE_IN_RMS_THRESHOLD) {
            if (bargeInStartRef.current === null) bargeInStartRef.current = performance.now();
            if (performance.now() - bargeInStartRef.current > BARGE_IN_SUSTAIN_MS) {
              interruptAndListen();
              return;
            }
          } else {
            bargeInStartRef.current = null;
          }
          rafRef.current = requestAnimationFrame(watchForBargeIn);
        };
        rafRef.current = requestAnimationFrame(watchForBargeIn);

        try {
          await audio.play();
        } catch {
          // play() rejects if interruptAndListen() already called pause() on
          // it — expected when the visitor talks right at playback start,
          // not a real failure.
        }
      } catch (err) {
        onError?.(err instanceof Error ? err.message : String(err));
        if (activeRef.current) startListening();
      }
    };
    recorder.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onUtterance, onError, startListening]);

  const startCall = useCallback(async () => {
    try {
      // Explicit (not just `audio: true`) because barge-in now watches this
      // same mic stream while the twin's own reply plays through the
      // speakers — echo cancellation is what keeps that playback from being
      // picked up as "the visitor is talking" and self-interrupting.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      analyserRef.current = analyser;
      activeRef.current = true;
      startListening();
    } catch (err) {
      setStatus("error");
      onError?.(
        err instanceof Error
          ? `Couldn't access the microphone: ${err.message}`
          : "Couldn't access the microphone."
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startListening, onError]);

  const endCall = useCallback(() => {
    activeRef.current = false;
    stopMonitorLoop();
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.onstop = null;
      recorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close().catch(() => {});
    playerRef.current?.pause();
    streamRef.current = null;
    audioCtxRef.current = null;
    analyserRef.current = null;
    recorderRef.current = null;
    playerRef.current = null;
    setStatus("idle");
    setVolume(0);
  }, []);

  return { status, volume, startCall, endCall };
}
