"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { TrackballControls } from "three/examples/jsm/controls/TrackballControls.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";

type BodyMeshViewerProps = {
  meshUrl: string;
};

type ViewPreset = "reset" | "front" | "side" | "top";

type ViewerActions = {
  applyPreset: (preset: ViewPreset) => void;
};

export function BodyMeshViewer({ meshUrl }: BodyMeshViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerActionsRef = useRef<ViewerActions | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [activePreset, setActivePreset] = useState<ViewPreset | null>("reset");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#f5efe4");

    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
    camera.position.set(0, 0.8, 2.4);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const controls = new TrackballControls(camera, renderer.domElement);
    controls.rotateSpeed = 4.4;
    controls.zoomSpeed = 1.15;
    controls.panSpeed = 0.9;
    controls.dynamicDampingFactor = 0.14;
    controls.noPan = false;
    controls.noZoom = false;
    controls.noRotate = false;
    controls.target.set(0, 0.75, 0);

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.1);
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
    keyLight.position.set(1.8, 2.2, 2.4);
    const rimLight = new THREE.DirectionalLight(0xfff1d6, 0.8);
    rimLight.position.set(-1.5, 1.2, -1.4);
    scene.add(ambientLight, keyLight, rimLight);

    const grid = new THREE.GridHelper(4, 12, 0xcdbba0, 0xe6dcc8);
    grid.position.y = -1.15;
    scene.add(grid);

    let object: THREE.Object3D | null = null;
    let frameId = 0;
    let defaultView: { direction: THREE.Vector3; up: THREE.Vector3 } = {
      direction: new THREE.Vector3(1, 0.38, 1),
      up: new THREE.Vector3(0, 1, 0),
    };

    const fitCamera = (direction: THREE.Vector3, up = new THREE.Vector3(0, 1, 0)) => {
      if (object === null) {
        return;
      }
      const box = new THREE.Box3().setFromObject(object);
      if (box.isEmpty()) {
        return;
      }
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      const radius = Math.max(sphere.radius, 0.18);
      const center = sphere.center.clone();
      const cameraDistance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
      const viewDirection = direction.clone().normalize();

      camera.up.copy(up.clone().normalize());
      camera.position.copy(center).add(viewDirection.multiplyScalar(cameraDistance * 1.18));
      camera.near = Math.max(cameraDistance / 250, 0.01);
      camera.far = Math.max(cameraDistance * 20, 100);
      camera.lookAt(center);
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();

      grid.position.y = box.min.y - 0.015;
    };

    const applyPreset = (preset: ViewPreset) => {
      if (object === null) {
        return;
      }
      switch (preset) {
        case "reset":
          fitCamera(defaultView.direction, defaultView.up);
          break;
        case "front":
          fitCamera(new THREE.Vector3(0, 0.08, 1), new THREE.Vector3(0, 1, 0));
          break;
        case "side":
          fitCamera(new THREE.Vector3(1, 0.08, 0), new THREE.Vector3(0, 1, 0));
          break;
        case "top":
          fitCamera(new THREE.Vector3(0, 1, 0.01), new THREE.Vector3(0, 0, -1));
          break;
      }
      setActivePreset(preset);
    };

    const resize = () => {
      const { clientWidth, clientHeight } = container;
      if (!clientWidth || !clientHeight) {
        return;
      }
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / clientHeight;
      camera.updateProjectionMatrix();
      controls.handleResize();
    };

    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frameId = window.requestAnimationFrame(animate);
    };

    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);
    const markCustomView = () => setActivePreset(null);
    controls.addEventListener("start", markCustomView);

    const handleDoubleClick = () => applyPreset("reset");
    renderer.domElement.addEventListener("dblclick", handleDoubleClick);

    viewerActionsRef.current = {
      applyPreset,
    };

    const loader = new OBJLoader();
    setStatus("loading");
    setErrorMessage("");
    setActivePreset("reset");
    loader.load(
      meshUrl,
      (loadedObject: THREE.Group) => {
        if (object !== null) {
          scene.remove(object);
        }
        loadedObject.traverse((child: THREE.Object3D) => {
          if (child instanceof THREE.Mesh) {
            child.material = new THREE.MeshStandardMaterial({
              color: "#d98b4f",
              roughness: 0.78,
              metalness: 0.06,
            });
          }
        });
        object = loadedObject;
        scene.add(loadedObject);
        defaultView = {
          direction: new THREE.Vector3(1, 0.38, 1),
          up: new THREE.Vector3(0, 1, 0),
        };
        applyPreset("reset");
        setStatus("ready");
      },
      undefined,
      (error: unknown) => {
        setStatus("error");
        setErrorMessage(error instanceof Error ? error.message : "无法加载 OBJ");
      },
    );

    animate();

    return () => {
      resizeObserver.disconnect();
      window.cancelAnimationFrame(frameId);
      viewerActionsRef.current = null;
      controls.removeEventListener("start", markCustomView);
      renderer.domElement.removeEventListener("dblclick", handleDoubleClick);
      controls.dispose();
      renderer.dispose();
      scene.clear();
      container.removeChild(renderer.domElement);
    };
  }, [meshUrl]);

  return (
    <div className="body-mesh-viewer">
      <div className="body-mesh-toolbar">
        <div className="body-mesh-toolbar-group">
          <button
            type="button"
            className={`pill-button ${activePreset === "reset" ? "accent" : ""}`}
            onClick={() => viewerActionsRef.current?.applyPreset("reset")}
            disabled={status !== "ready"}
          >
            重置
          </button>
          <button
            type="button"
            className={`pill-button ${activePreset === "front" ? "accent" : ""}`}
            onClick={() => viewerActionsRef.current?.applyPreset("front")}
            disabled={status !== "ready"}
          >
            正面
          </button>
          <button
            type="button"
            className={`pill-button ${activePreset === "side" ? "accent" : ""}`}
            onClick={() => viewerActionsRef.current?.applyPreset("side")}
            disabled={status !== "ready"}
          >
            侧面
          </button>
          <button
            type="button"
            className={`pill-button ${activePreset === "top" ? "accent" : ""}`}
            onClick={() => viewerActionsRef.current?.applyPreset("top")}
            disabled={status !== "ready"}
          >
            俯视
          </button>
        </div>
        <span className="body-mesh-toolbar-hint">拖拽旋转 · 右键平移 · 滚轮缩放 · 双击重置</span>
      </div>
      <div ref={containerRef} className="body-mesh-canvas" />
      {status !== "ready" ? (
        <div className="body-mesh-overlay">
          <strong>{status === "loading" ? "正在加载 3D mesh…" : "3D 预览失败"}</strong>
          {status === "error" ? <span>{errorMessage}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
