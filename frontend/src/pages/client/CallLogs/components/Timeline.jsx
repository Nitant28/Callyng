import './Timeline.css';

const Timeline = ({ label }) => (
  <div className="cl-timeline">
    <span className="cl-timeline__label">{label}</span>
    <span className="cl-timeline__line" />
  </div>
);

export default Timeline;
