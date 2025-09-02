import * as THREE from "three";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const SHOW_GRID = false; // set to true if you want it; off avoids visual clutter/flicker

function project([lon, lat], refLat = 51.05) {
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos((refLat * Math.PI) / 180);
  return [lon * mPerDegLon, lat * mPerDegLat];
}

function getGeoCenter(features) {
  if (!features?.length) return [-114.0719, 51.0447]; // downtown fallback
  const g = features[0]?.geometry;
  const polys = g?.type === "MultiPolygon" ? g.coordinates : g?.coordinates ? [g.coordinates] : [];
  const ring = polys[0]?.[0];
  if (!ring?.length) return [-114.0719, 51.0447];
  let sx = 0, sy = 0;
  for (const pt of ring) { sx += pt[0]; sy += pt[1]; }
  return [sx / ring.length, sy / ring.length];
}

function featureToMesh(feature, originXY, highlight = false) {
  const g = feature.geometry;
  if (!g) return null;
  const polygons = g.type === "MultiPolygon" ? g.coordinates : [g.coordinates];
  const refLat = feature.properties?.__refLat ?? 51.05;

  const first = polygons[0];
  if (!first || !first[0]?.length) return null;

  const shape = new THREE.Shape();
  const outer = first[0];
  outer.forEach((pt, i) => {
    const [px, py] = project(pt, refLat);
    const x = px - originXY[0];
    const y = py - originXY[1];
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  });

  for (let h = 1; h < first.length; h++) {
    const holePts = first[h];
    if (!holePts?.length) continue;
    const holePath = new THREE.Path();
    holePts.forEach((pt, i) => {
      const [px, py] = project(pt, refLat);
      const x = px - originXY[0];
      const y = py - originXY[1];
      if (i === 0) holePath.moveTo(x, y);
      else holePath.lineTo(x, y);
    });
    shape.holes.push(holePath);
  }

  const height = Math.max(1, Number(feature.properties?.height_m || 10));
  const geom = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
  geom.rotateX(Math.PI / 2); // make Y up
  // leave normals as-is; computing them is heavier and not needed for Lambert

  // OPAQUE material (no transparency -> fewer sorting artifacts)
  const mat = new THREE.MeshLambertMaterial({
    color: highlight ? 0xff5533 : 0x8aa1c1,
    depthWrite: true,
    depthTest: true,
  });

  const mesh = new THREE.Mesh(geom, mat);
  mesh.userData = { id: feature.properties?.id, props: feature.properties };
  return mesh;
}

export default function Scene3D({ features = [], highlightIds = new Set() }) {
  const mountRef = useRef(null);
  const rendererRef = useRef(null);
  const sceneRef = useRef(new THREE.Scene());
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const groupRef = useRef(new THREE.Group());
  const rayRef = useRef(new THREE.Raycaster());
  const mouseRef = useRef(new THREE.Vector2());
  const needsPickRef = useRef(false);
  const rafIdRef = useRef(0);

  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);

  const origin = useMemo(() => {
    const [lon, lat] = getGeoCenter(features);
    return project([lon, lat]);
  }, [features]);

  useEffect(() => {
    const mount = mountRef.current;

    // clamp pixel ratio to reduce shimmer on HiDPI
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.autoClear = true;
    mount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const scene = sceneRef.current;
    scene.background = new THREE.Color(0xf8fafc);

    // narrower frustum -> better depth precision (less z-fighting)
    const camera = new THREE.PerspectiveCamera(55, mount.clientWidth / mount.clientHeight, 1, 50000);
    camera.up.set(0, 1, 0);
    camera.position.set(800, 900, 800);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minPolarAngle = 0.05;
    controls.enablePan = true;
    controls.screenSpacePanning = false;
    controlsRef.current = controls;

    // lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.85));
    const sun = new THREE.DirectionalLight(0xffffff, 0.9);
    sun.position.set(300, 800, 500);
    scene.add(sun);

    // ground slightly below zero + polygon offset -> avoids z-fight with building bases
    const groundMat = new THREE.MeshLambertMaterial({
      color: 0xe2e8f0,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    });
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(50000, 50000), groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, -2, 0); // push down 2m
    scene.add(ground);

    if (SHOW_GRID) {
      const grid = new THREE.GridHelper(20000, 100, 0xcbd5e1, 0xe2e8f0);
      grid.position.y = -1.9; // below building bases, just above ground
      scene.add(grid);
    }

    groupRef.current = new THREE.Group();
    scene.add(groupRef.current);

    const onResize = () => {
      const w = mount.clientWidth, h = mount.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      needsPickRef.current = true;
    };
    window.addEventListener("resize", onResize);

    const onMove = (ev) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouseRef.current.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      mouseRef.current.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      needsPickRef.current = true; // pick only when mouse moves
    };
    const onClick = () => {
      rayRef.current.setFromCamera(mouseRef.current, camera);
      const hits = rayRef.current.intersectObjects(groupRef.current.children, true);
      if (hits.length) setSelected(hits[0].object.userData?.props || null);
    };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("click", onClick);

    const tick = () => {
      controls.update();

      if (needsPickRef.current) {
        needsPickRef.current = false;
        rayRef.current.setFromCamera(mouseRef.current, camera);
        const hits = rayRef.current.intersectObjects(groupRef.current.children, true);
        setHovered(hits.length ? (hits[0].object.userData?.props || null) : null);
      }

      renderer.render(scene, camera);
      rafIdRef.current = requestAnimationFrame(tick);
    };
    rafIdRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafIdRef.current);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("click", onClick);
      renderer.dispose();
      if (renderer.domElement && renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []);

  // rebuild meshes on data/highlights change
  useEffect(() => {
    const grp = groupRef.current;
    if (!grp) return;
    while (grp.children.length) grp.remove(grp.children[0]);

    for (const f of features) {
      const isHi = f?.properties && highlightIds.has(f.properties.id);
      const mesh = featureToMesh(f, origin, isHi);
      if (mesh) grp.add(mesh);
    }
    needsPickRef.current = true;
  }, [features, highlightIds, origin]);

  const Card = ({ title, children, style }) => (
    <div style={{
      position: "absolute", right: 12, padding: "10px 12px", minWidth: 260,
      background: "rgba(255,255,255,0.95)", border: "1px solid #e5e7eb", borderRadius: 10,
      boxShadow: "0 6px 18px rgba(0,0,0,0.08)", ...style
    }}>
      {title && <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>}
      <div style={{ fontSize: 13, lineHeight: 1.35 }}>{children}</div>
    </div>
  );

  const InfoRows = ({ p }) => (!p ? null : (
    <>
      <div><b>Address:</b> {p.address || "—"}</div>
      <div><b>Zoning:</b> {p.zoning || "—"}</div>
      <div><b>Assessment:</b> {p.assessed_value ? `$${Number(p.assessed_value).toLocaleString()}` : "—"}</div>
      <div><b>Community:</b> {p.community || "—"}</div>
      {"year" in p && <div><b>Year:</b> {p.year ?? "—"}</div>}
      <div><b>ID:</b> {p.id || "—"}</div>
    </>
  ));

  return (
    <div ref={mountRef} style={{ width: "100%", height: "100%", position: "relative" }}>
      {hovered && !selected && (
        <Card title="Hover" style={{ top: 12 }}>
          <InfoRows p={hovered} />
        </Card>
      )}
      {selected && (
        <Card title="Selected" style={{ top: hovered ? 160 : 12 }}>
          <InfoRows p={selected} />
          <div style={{ marginTop: 8 }}>
            <button
              onClick={() => setSelected(null)}
              style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#f8fafc", cursor: "pointer" }}
            >Clear</button>
          </div>
        </Card>
      )}
    </div>
  );
}
