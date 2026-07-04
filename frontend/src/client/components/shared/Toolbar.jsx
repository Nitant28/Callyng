import React from 'react';

const Toolbar = ({ left, right, style }) => {
  return (
    <div className="cl-lead-toolbar" style={style}>
      <div className="cl-lead-toolbar__left">
        {left}
      </div>
      {right && (
        <div className="cl-lead-toolbar__right">
          {right}
        </div>
      )}
    </div>
  );
};

export default Toolbar;
