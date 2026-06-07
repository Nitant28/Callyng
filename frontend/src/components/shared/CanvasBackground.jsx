import { useEffect, useRef } from 'react';

const CanvasBackground = () => {
  const bgRef = useRef(null);

  useEffect(() => {
    const bgCanvas = bgRef.current;
    if (!bgCanvas) return;

    // --- Plexus Mesh Canvas ---
    const ctx = bgCanvas.getContext('2d');
    let width, height, points = [];
    let mouse = { x: -1000, y: -1000 };

    const initBgCanvas = () => {
      width = bgCanvas.width = window.innerWidth;
      height = bgCanvas.height = window.innerHeight;
      points = [];
      const numPoints = Math.floor((width * height) / 15000);
      for (let i = 0; i < numPoints; i++) {
        points.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.5,
          vy: (Math.random() - 0.5) * 0.5,
          baseX: Math.random() * width,
          baseY: Math.random() * height
        });
      }
    };

    const handleMouseMove = (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    const handleMouseLeave = () => {
      mouse.x = -1000;
      mouse.y = -1000;
    };

    window.addEventListener('resize', initBgCanvas);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseleave', handleMouseLeave);

    let bgAnimFrameId;
    const animateBg = () => {
      ctx.clearRect(0, 0, width, height);

      const isDark = document.documentElement.classList.contains('dark');
      const colorRgb = isDark ? '77, 117, 250' : '0, 49, 185';
      const hoverColorRgb = isDark ? '255, 122, 60' : '22, 71, 232';

      points.forEach((p, i) => {
        p.x += p.vx;
        p.y += p.vy;

        // Mouse interaction - repel
        const dxMouse = mouse.x - p.x;
        const dyMouse = mouse.y - p.y;
        const distMouse = Math.sqrt(dxMouse * dxMouse + dyMouse * dyMouse);

        if (distMouse < 150) {
          const force = (150 - distMouse) / 150;
          p.x -= (dxMouse / distMouse) * force * 2;
          p.y -= (dyMouse / distMouse) * force * 2;
        }

        // Bounce off walls gently
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;

        // Keep within bounds
        p.x = Math.max(0, Math.min(width, p.x));
        p.y = Math.max(0, Math.min(height, p.y));

        // Draw Nodes
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2);
        ctx.fillStyle = distMouse < 150 ? `rgba(${hoverColorRgb}, 0.8)` : `rgba(${colorRgb}, 0.3)`;
        ctx.fill();

        // Draw Lines
        points.forEach((p2, j) => {
          if (i >= j) return;
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            const opacity = (1 - dist / 120) * 0.2;
            ctx.strokeStyle = distMouse < 150 ? `rgba(${hoverColorRgb}, ${opacity * 2})` : `rgba(${colorRgb}, ${opacity})`;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        });
      });

      bgAnimFrameId = requestAnimationFrame(animateBg);
    };

    initBgCanvas();
    animateBg();

    return () => {
      window.removeEventListener('resize', initBgCanvas);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
      cancelAnimationFrame(bgAnimFrameId);
    };
  }, []);

  return (
    <canvas ref={bgRef} id="bg-canvas" />
  );
};

export default CanvasBackground;
