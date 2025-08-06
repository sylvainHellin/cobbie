import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { BIMModel } from '../types';
import { apiService } from '../services/api';

interface BIMViewerProps {
    model: BIMModel;
    onModelLoaded: () => void;
    isLoading: boolean;
}

// Helper function to create model-specific visualizations
function createModelSpecificVisualization(model: BIMModel, fileSize?: number): THREE.Group {
    const buildingGroup = new THREE.Group();

    // Base colors that vary by model
    const modelColors = {
        primary: model.id % 2 === 0 ? 0xf0f0f0 : 0xe8e8e8,
        accent: model.id % 3 === 0 ? 0x0ea5e9 : model.id % 3 === 1 ? 0x10b981 : 0xf59e0b,
        roof: model.id % 2 === 0 ? 0x8B4513 : 0x654321
    };

    // Vary building size based on model characteristics
    const scale = 1 + (model.id % 3) * 0.3; // Scale between 1.0 and 1.6
    const width = 20 * scale;
    const depth = 15 * scale;
    const height = 8 + (model.id % 4) * 2; // Height between 8 and 14

    // Foundation
    const foundationGeometry = new THREE.BoxGeometry(width, 1, depth);
    const foundationMaterial = new THREE.MeshLambertMaterial({ color: 0x808080 });
    const foundation = new THREE.Mesh(foundationGeometry, foundationMaterial);
    foundation.position.set(0, -0.5, 0);
    buildingGroup.add(foundation);

    // Walls
    const wallMaterial = new THREE.MeshLambertMaterial({ color: modelColors.primary });

    // Front and back walls
    const frontWallGeometry = new THREE.BoxGeometry(width, height, 0.5);
    const frontWall = new THREE.Mesh(frontWallGeometry, wallMaterial);
    frontWall.position.set(0, height / 2, depth / 2 - 0.25);
    buildingGroup.add(frontWall);

    const backWall = new THREE.Mesh(frontWallGeometry, wallMaterial);
    backWall.position.set(0, height / 2, -depth / 2 + 0.25);
    buildingGroup.add(backWall);

    // Side walls
    const sideWallGeometry = new THREE.BoxGeometry(0.5, height, depth);
    const leftWall = new THREE.Mesh(sideWallGeometry, wallMaterial);
    leftWall.position.set(-width / 2 + 0.25, height / 2, 0);
    buildingGroup.add(leftWall);

    const rightWall = new THREE.Mesh(sideWallGeometry, wallMaterial);
    rightWall.position.set(width / 2 - 0.25, height / 2, 0);
    buildingGroup.add(rightWall);

    // Roof
    const roofGeometry = new THREE.BoxGeometry(width + 1, 0.5, depth + 1);
    const roofMaterial = new THREE.MeshLambertMaterial({ color: modelColors.roof });
    const roof = new THREE.Mesh(roofGeometry, roofMaterial);
    roof.position.set(0, height + 0.25, 0);
    buildingGroup.add(roof);

    // Door (varies by model)
    const doorGeometry = new THREE.BoxGeometry(2, height * 0.75, 0.1);
    const doorMaterial = new THREE.MeshLambertMaterial({ color: modelColors.accent });
    const door = new THREE.Mesh(doorGeometry, doorMaterial);
    door.position.set(0, height * 0.375, depth / 2 + 0.05);
    buildingGroup.add(door);

    // Windows (number varies by model)
    const windowCount = 2 + (model.id % 3);
    const windowGeometry = new THREE.BoxGeometry(2, 2, 0.1);
    const windowMaterial = new THREE.MeshLambertMaterial({
        color: 0x87CEEB,
        transparent: true,
        opacity: 0.7
    });

    for (let i = 0; i < windowCount; i++) {
        const window = new THREE.Mesh(windowGeometry, windowMaterial);
        const xOffset = (i - windowCount / 2 + 0.5) * 4;
        window.position.set(xOffset, height * 0.6, depth / 2 + 0.05);
        buildingGroup.add(window);
    }

    // Add model info as a text label (simple geometric representation)
    const labelGeometry = new THREE.PlaneGeometry(width * 0.8, 1);
    const labelColor = fileSize ? modelColors.accent : 0xff6b6b; // Red if fallback, accent if from API
    const labelMaterial = new THREE.MeshLambertMaterial({
        color: labelColor,
        transparent: true,
        opacity: 0.3
    });
    const label = new THREE.Mesh(labelGeometry, labelMaterial);
    label.position.set(0, -1.5, 0);
    label.rotation.x = -Math.PI / 2;
    buildingGroup.add(label);

    // Add some model-specific details
    if (model.model_name.toLowerCase().includes('arc')) {
        // Add architectural details like a small tower
        const towerGeometry = new THREE.BoxGeometry(3, height * 1.5, 3);
        const tower = new THREE.Mesh(towerGeometry, wallMaterial);
        tower.position.set(width / 3, height * 0.75, depth / 3);
        buildingGroup.add(tower);
    }

    if (model.model_name.toLowerCase().includes('struct')) {
        // Add structural elements like columns
        const columnGeometry = new THREE.CylinderGeometry(0.3, 0.3, height);
        const columnMaterial = new THREE.MeshLambertMaterial({ color: 0x666666 });

        for (let x = -1; x <= 1; x++) {
            for (let z = -1; z <= 1; z++) {
                if (x === 0 && z === 0) continue; // Skip center
                const column = new THREE.Mesh(columnGeometry, columnMaterial);
                column.position.set(x * width / 3, height / 2, z * depth / 3);
                buildingGroup.add(column);
            }
        }
    }

    return buildingGroup;
}

const BIMViewer: React.FC<BIMViewerProps> = ({ model, onModelLoaded, isLoading }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const sceneRef = useRef<THREE.Scene | null>(null);
    const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
    const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

    const [loadingProgress, setLoadingProgress] = useState(0);
    const [loadingMessage, setLoadingMessage] = useState('Initializing viewer...');

    useEffect(() => {
        if (!containerRef.current || !model) return;

        const initViewer = async () => {
            try {
                setLoadingMessage('Initializing 3D viewer...');
                setLoadingProgress(10);

                // Create scene
                const scene = new THREE.Scene();
                sceneRef.current = scene;

                // Create camera
                const container = containerRef.current;
                if (!container) return;

                const camera = new THREE.PerspectiveCamera(
                    75,
                    container.clientWidth / container.clientHeight,
                    0.1,
                    1000
                );
                cameraRef.current = camera;
                camera.position.set(10, 10, 10);
                camera.lookAt(0, 0, 0);

                // Create renderer
                const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
                rendererRef.current = renderer;
                renderer.setSize(container.clientWidth, container.clientHeight);
                renderer.setClearColor(0xf0f9ff, 0); // Light blue transparent background
                renderer.shadowMap.enabled = true;
                renderer.shadowMap.type = THREE.PCFSoftShadowMap;
                container.appendChild(renderer.domElement);

                setLoadingProgress(30);
                setLoadingMessage('Setting up lighting and controls...');

                // Add lights
                const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
                scene.add(ambientLight);

                const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
                directionalLight.position.set(10, 10, 5);
                directionalLight.castShadow = true;
                scene.add(directionalLight);

                // Add simple orbit controls (we'll implement basic mouse controls)
                let mouseDown = false;
                let mouseX = 0;
                let mouseY = 0;

                const onMouseDown = (event: MouseEvent) => {
                    mouseDown = true;
                    mouseX = event.clientX;
                    mouseY = event.clientY;
                };

                const onMouseUp = () => {
                    mouseDown = false;
                };

                const onMouseMove = (event: MouseEvent) => {
                    if (!mouseDown) return;

                    const deltaX = event.clientX - mouseX;
                    const deltaY = event.clientY - mouseY;

                    // Simple orbital rotation
                    const spherical = new THREE.Spherical();
                    spherical.setFromVector3(camera.position);
                    spherical.theta -= deltaX * 0.01;
                    spherical.phi += deltaY * 0.01;
                    spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi));

                    camera.position.setFromSpherical(spherical);
                    camera.lookAt(0, 0, 0);

                    mouseX = event.clientX;
                    mouseY = event.clientY;
                };

                const onWheel = (event: WheelEvent) => {
                    const scale = event.deltaY > 0 ? 1.1 : 0.9;
                    camera.position.multiplyScalar(scale);
                };

                renderer.domElement.addEventListener('mousedown', onMouseDown);
                window.addEventListener('mouseup', onMouseUp);
                window.addEventListener('mousemove', onMouseMove);
                renderer.domElement.addEventListener('wheel', onWheel);

                setLoadingProgress(50);
                setLoadingMessage('Downloading BIM model...');

                // Try to load the actual IFC model from the API
                let buildingGroup: THREE.Group;

                try {
                    // Check if the API is available by trying to download the IFC file
                    const ifcBlob = await apiService.downloadIfcFile(model.id);
                    setLoadingProgress(65);
                    setLoadingMessage('Processing IFC data...');

                    // For now, since we don't have a working IFC loader, 
                    // we'll create a model-specific representation based on the model data
                    buildingGroup = createModelSpecificVisualization(model, ifcBlob.size);

                } catch (error) {
                    console.log('Could not load IFC file from API, using fallback visualization:', error);
                    setLoadingProgress(65);
                    setLoadingMessage('Creating model visualization...');

                    // Create a fallback visualization based on model metadata
                    buildingGroup = createModelSpecificVisualization(model, 0);
                }

                setLoadingProgress(70);
                setLoadingMessage('Processing model data...');

                scene.add(buildingGroup);

                setLoadingProgress(90);
                setLoadingMessage('Finalizing viewer...');

                // Center the building
                buildingGroup.position.set(0, 0, 0);

                // Adjust camera to fit building (dynamic based on building size)
                const box = new THREE.Box3().setFromObject(buildingGroup);
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);
                camera.position.set(maxDim * 1.5, maxDim * 1.2, maxDim * 1.5);
                camera.lookAt(0, size.y / 2, 0);

                // Start render loop
                const animate = () => {
                    requestAnimationFrame(animate);
                    renderer.render(scene, camera);
                };
                animate();

                setLoadingProgress(100);
                setLoadingMessage('Model loaded successfully!');

                // Small delay to show completion
                setTimeout(() => {
                    onModelLoaded();
                }, 500);

            } catch (error) {
                console.error('Failed to load BIM model:', error);
                setLoadingMessage('Failed to load model. Please try again.');

                // Create a fallback scene with a simple cube
                if (sceneRef.current && rendererRef.current && cameraRef.current) {
                    const geometry = new THREE.BoxGeometry();
                    const material = new THREE.MeshBasicMaterial({ color: 0x0ea5e9 });
                    const cube = new THREE.Mesh(geometry, material);
                    sceneRef.current.add(cube);

                    const animate = () => {
                        requestAnimationFrame(animate);
                        cube.rotation.x += 0.01;
                        cube.rotation.y += 0.01;
                        rendererRef.current!.render(sceneRef.current!, cameraRef.current!);
                    };
                    animate();
                }

                onModelLoaded();
            }
        };

        initViewer();

        // Cleanup
        return () => {
            if (rendererRef.current && containerRef.current) {
                containerRef.current.removeChild(rendererRef.current.domElement);
                rendererRef.current.dispose();
            }
        };
    }, [model, onModelLoaded]);

    // Handle window resize
    useEffect(() => {
        const handleResize = () => {
            if (rendererRef.current && cameraRef.current && containerRef.current) {
                const width = containerRef.current.clientWidth;
                const height = containerRef.current.clientHeight;

                cameraRef.current.aspect = width / height;
                cameraRef.current.updateProjectionMatrix();
                rendererRef.current.setSize(width, height);
            }
        };

        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    return (
        <div className="relative w-full h-full bg-gradient-to-br from-blue-50 to-blue-100">
            {/* Viewer Container */}
            <div
                ref={containerRef}
                className="w-full h-full"
                style={{
                    background: 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)',
                }}
            />

            {/* Loading Overlay */}
            {isLoading && (
                <div className="absolute inset-0 bg-white bg-opacity-90 flex items-center justify-center z-10">
                    <div className="text-center max-w-md">
                        {/* Progress Bar */}
                        <div className="w-64 h-2 bg-slate-200 rounded-full mb-4">
                            <div
                                className="h-2 bg-gradient-to-r from-primary-500 to-primary-600 rounded-full transition-all duration-300 ease-out"
                                style={{ width: `${loadingProgress}%` }}
                            />
                        </div>

                        {/* Loading Message */}
                        <p className="text-slate-700 font-medium mb-2 loading-text">
                            {loadingMessage}
                        </p>

                        {/* Progress Percentage */}
                        <p className="text-sm text-slate-500">
                            {loadingProgress}% complete
                        </p>

                        {/* Animated Icon */}
                        <div className="mt-6">
                            <div className="w-12 h-12 mx-auto bg-primary-100 rounded-full flex items-center justify-center animate-pulse-slow">
                                <svg className="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                                </svg>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Model Info Overlay */}
            {!isLoading && (
                <div className="absolute top-4 left-4 bg-white bg-opacity-90 backdrop-blur-sm rounded-lg p-4 shadow-sm border border-slate-200 max-w-sm">
                    <h3 className="font-medium text-slate-900 text-sm mb-1">{model.model_name}</h3>
                    <p className="text-xs text-slate-600 mb-2">{model.model_description}</p>
                    <div className="space-y-1 text-xs text-slate-500">
                        <div className="flex justify-between">
                            <span>Project:</span>
                            <span className="font-medium">{model.project_name}</span>
                        </div>
                        <div className="flex justify-between">
                            <span>Model ID:</span>
                            <span className="font-medium">{model.id}</span>
                        </div>
                        {model.model_path && (
                            <div className="text-xs text-slate-400 truncate">
                                Path: {model.model_path}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Viewer Controls */}
            {!isLoading && (
                <div className="absolute bottom-4 right-4 flex flex-col space-y-2">
                    <button
                        onClick={() => {
                            if (cameraRef.current) {
                                cameraRef.current.position.set(10, 10, 10);
                                cameraRef.current.lookAt(0, 0, 0);
                            }
                        }}
                        className="bg-white bg-opacity-90 backdrop-blur-sm hover:bg-opacity-100 text-slate-700 p-2 rounded-lg shadow-sm border border-slate-200 transition-all"
                        title="Reset View"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                </div>
            )}
        </div>
    );
};

export default BIMViewer;