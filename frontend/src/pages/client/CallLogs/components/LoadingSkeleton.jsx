import './LoadingSkeleton.css';

const LoadingSkeleton = ({ count = 6 }) => (
  <div className="cl-skeleton-list">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="cl-skeleton-card">
        <div className="ds-shimmer cl-skeleton-card__avatar" />
        <div className="cl-skeleton-card__lines">
          <div className="ds-shimmer" style={{ height: 14, width: '40%' }} />
          <div className="ds-shimmer" style={{ height: 12, width: '55%', marginTop: 8 }} />
          <div className="ds-shimmer" style={{ height: 12, width: '30%', marginTop: 10 }} />
        </div>
      </div>
    ))}
  </div>
);

export default LoadingSkeleton;
