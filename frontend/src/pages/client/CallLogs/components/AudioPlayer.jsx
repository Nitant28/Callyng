import { useEffect, useRef, useState } from 'react';
import './AudioPlayer.css';

const WAVEFORM = [4, 8, 12, 6, 14, 10, 16, 8, 12, 6, 14, 10, 8, 12, 6, 18, 10, 8, 14, 6, 12, 8, 10, 16];

const formatTime = (sec) => {
  if (!Number.isFinite(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
};

const AudioPlayer = ({ src, loading, error, downloadName }) => {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);

  useEffect(() => {
    setPlaying(false);
    setCurrent(0);
    setDuration(0);
  }, [src]);

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) el.pause();
    else el.play();
    setPlaying(!playing);
  };

  const cycleRate = () => {
    const next = rate === 1 ? 1.25 : rate === 1.25 ? 1.5 : rate === 1.5 ? 2 : 1;
    setRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  };

  if (loading) {
    return (
      <div className="cl-audio cl-audio--loading">
        <span className="material-symbols-outlined cl-spin">progress_activity</span>
        Loading recording…
      </div>
    );
  }

  if (!src) {
    return (
      <div className="cl-audio cl-audio--empty">
        {error || 'Recording will appear when the call completes.'}
      </div>
    );
  }

  const progress = duration > 0 ? (current / duration) * 100 : 0;

  return (
    <div className="cl-audio">
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={(e) => setCurrent(e.target.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.target.duration)}
        onEnded={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />
      <button type="button" className="cl-audio__play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>
        <span className="material-symbols-outlined">{playing ? 'pause' : 'play_arrow'}</span>
      </button>
      <div className="cl-audio__track">
        <div className="cl-audio__wave">
          {WAVEFORM.map((h, i) => (
            <span
              key={i}
              className={`cl-audio__bar ${(i / WAVEFORM.length) * 100 < progress ? 'cl-audio__bar--played' : ''}`}
              style={{ height: `${h}px` }}
            />
          ))}
        </div>
        <input
          type="range"
          className="cl-audio__seek"
          min={0}
          max={duration || 100}
          value={current}
          onChange={(e) => {
            const t = Number(e.target.value);
            setCurrent(t);
            if (audioRef.current) audioRef.current.currentTime = t;
          }}
        />
        <div className="cl-audio__times">
          <span>{formatTime(current)}</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>
      <button type="button" className="cl-audio__rate" onClick={cycleRate}>{rate}x</button>
      <a
        href={src}
        download={downloadName || 'recording.mp3'}
        className="cl-audio__dl"
        title="Download"
      >
        <span className="material-symbols-outlined">download</span>
      </a>
    </div>
  );
};

export default AudioPlayer;
