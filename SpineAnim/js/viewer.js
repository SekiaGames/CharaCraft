class SpineViewer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl2', { alpha: true, antialias: true, premultipliedAlpha: false })
      || canvas.getContext('webgl', { alpha: true, antialias: true, premultipliedAlpha: false });
    if (!this.gl) throw new Error('这个浏览器开不了 WebGL');
    this.renderer = new spine.SceneRenderer(canvas, this.gl, false);
    this.debug = this.renderer.skeletonDebugRenderer;
    this.debug.drawBones = true;
    this.debug.drawRegionAttachments = false;
    this.debug.drawMeshHull = false;
    this.debug.drawMeshTriangles = false;
    this.debug.drawPaths = false;
    this.debug.drawBoundingBoxes = false;
    this.debug.drawClipping = false;
    this.debug.boneLineColor.set(0.06, 0.45, 0.38, 0.9);
    this.debug.boneOriginColor.set(0.85, 0.35, 0.2, 0.9);
    this.clipper = this.renderer.skeletonRenderer.getSkeletonClipping();
    this.dpr = Math.min(window.devicePixelRatio || 1, 3);
    this.resize();
  }

  resize() {
    const width = Math.max(1, Math.round(this.canvas.clientWidth * this.dpr));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * this.dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.renderer.camera.setViewport(this.canvas.width, this.canvas.height);
    this.renderer.camera.update();
  }

  worldAt(px, py) {
    const cam = this.renderer.camera;
    return {
      x: cam.position.x + (px - this.canvas.width / 2) * cam.zoom,
      y: cam.position.y - (py - this.canvas.height / 2) * cam.zoom,
    };
  }

  zoomAt(px, py, factor) {
    const cam = this.renderer.camera;
    const before = this.worldAt(px, py);
    cam.zoom = Math.min(64, Math.max(0.02, cam.zoom / factor));
    const after = this.worldAt(px, py);
    cam.position.x += before.x - after.x;
    cam.position.y += before.y - after.y;
    cam.update();
  }

  pan(dx, dy) {
    const cam = this.renderer.camera;
    cam.position.x -= dx * cam.zoom;
    cam.position.y += dy * cam.zoom;
    cam.update();
  }

  toScreen(wx, wy) {
    const cam = this.renderer.camera;
    const x = (wx - cam.position.x) / cam.zoom + this.canvas.width / 2;
    const y = this.canvas.height / 2 - (wy - cam.position.y) / cam.zoom;
    return { x: x / this.dpr, y: y / this.dpr };
  }

  worldDelta(x0, y0, x1, y1) {
    const zoom = this.renderer.camera.zoom * this.dpr;
    return { x: (x1 - x0) * zoom, y: -(y1 - y0) * zoom };
  }

  boneTip(bone) {
    const p = bone.appliedPose;
    const len = bone.data.length || 0;
    return { x: p.worldX + len * p.a, y: p.worldY + len * p.b };
  }

  pickBone(skeleton, x, y, radius = 20) {
    let best = null;
    let bestDistance = radius;
    for (const bone of skeleton.bones) {
      if (!bone.active) continue;
      const p = bone.appliedPose;
      const origin = this.toScreen(p.worldX, p.worldY);
      const d0 = Math.hypot(origin.x - x, origin.y - y);
      if (d0 < bestDistance) {
        bestDistance = d0;
        best = bone;
      }
      if (bone.data.length > 0) {
        const tip = this.boneTip(bone);
        const s = this.toScreen(tip.x, tip.y);
        const d1 = Math.hypot(s.x - x, s.y - y);
        if (d1 < bestDistance) {
          bestDistance = d1;
          best = bone;
        }
      }
    }
    return best;
  }

  toLocalDelta(parent, worldX, worldY) {
    if (!parent) return { x: worldX, y: worldY };
    const p = parent.appliedPose;
    const det = p.a * p.d - p.b * p.c;
    if (Math.abs(det) < 1e-6) return { x: worldX, y: worldY };
    return {
      x: (p.d * worldX - p.c * worldY) / det,
      y: (-p.b * worldX + p.a * worldY) / det,
    };
  }

  fit(skeleton, padding = 1.12) {
    if (!skeleton) return;
    const offset = new spine.Vector2();
    const size = new spine.Vector2();
    skeleton.getBounds(offset, size, new Array(2), this.clipper);
    const cam = this.renderer.camera;
    if (!Number.isFinite(size.x) || !Number.isFinite(size.y) || size.x <= 0 || size.y <= 0) {
      cam.zoom = 1;
      cam.position.set(0, 0, 0);
      cam.update();
      return;
    }
    const pad = padding || 1;
    const zoomX = (size.x * pad) / this.canvas.width;
    const zoomY = (size.y * pad) / this.canvas.height;
    cam.zoom = Math.max(zoomX, zoomY);
    cam.position.set(offset.x + size.x / 2, offset.y + size.y / 2, 0);
    cam.update();
  }

  render(skeleton, showBones) {
    const gl = this.gl;
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!skeleton) return;
    this.renderer.begin();
    this.renderer.drawSkeleton(skeleton);
    if (showBones) this.renderer.drawSkeletonDebug(skeleton);
    this.renderer.end();
  }
}
