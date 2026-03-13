"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

type ObjectGlbViewerProps = {
  glbUrl: string;
};

export function ObjectGlbViewer({ glbUrl }: ObjectGlbViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#f5efe4");

    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
    camera.position.set(0, 0.8, 2.6);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0.25, 0);

    scene.add(new THREE.AmbientLight(0xffffff, 1.15));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
    keyLight.position.set(1.8, 2.2, 2.4);
    const rimLight = new THREE.DirectionalLight(0xfff1d6, 0.8);
    rimLight.position.set(-1.5, 1.2, -1.4);
    scene.add(keyLight, rimLight);

    const grid = new THREE.GridHelper(4, 12, 0xcdbba0, 0xe6dcc8);
    grid.position.y = -1.15;
    scene.add(grid);

    let object: THREE.Object3D | null = null;
    let frameId = 0;

    const resize = () => {
      const { clientWidth, clientHeight } = container;
      if (!clientWidth || !clientHeight) {
        return;
      }
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / clientHeight;
      camera.updateProjectionMatrix();
    };

    const fitCamera = (targetObject: THREE.Object3D) => {
      const box = new THREE.Box3().setFromObject(targetObject);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const maxSize = Math.max(size.x, size.y, size.z, 0.1);
      const distance = maxSize / (2 * Math.tan((camera.fov * Math.PI) / 360));
      camera.position.set(center.x, center.y + size.y * 0.1, center.z + distance * 1.65);
      camera.near = Math.max(distance / 100, 0.01);
      camera.far = Math.max(distance * 10, 100);
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    };

    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frameId = window.requestAnimationFrame(animate);
    };

    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    setStatus("loading");
    setErrorMessage("");
    const loader = new GLTFLoader();
    loader.load(
      glbUrl,
      (gltf) => {
        if (object) {
          scene.remove(object);
        }
        object = gltf.scene;
        scene.add(gltf.scene);
        fitCamera(gltf.scene);
        setStatus("ready");
      },
      undefined,
      (error: unknown) => {
        setStatus("error");
        setErrorMessage(error instanceof Error ? error.message : "无法加载 GLB");
      },
    );

    animate();

    return () => {
      resizeObserver.disconnect();
      window.cancelAnimationFrame(frameId);
      controls.dispose();
      renderer.dispose();
      scene.clear();
      container.removeChild(renderer.domElement);
    };
  }, [glbUrl]);

  return (
    <div className="body-mesh-viewer">
      <div ref={containerRef} className="body-mesh-canvas" />
      {status !== "ready" ? (
        <div className="body-mesh-overlay">
          <strong>{status === "loading" ? "正在加载对象 3D…" : "对象 3D 预览失败"}</strong>
          {status === "error" ? <span>{errorMessage}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
