import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import * as OBC from '@thatopen/components';
import Stats from 'stats.js';
import { BIMModel } from '../types';
import { apiService } from '../services/api';

interface BIMViewerProps {
    selectedModel?: BIMModel;
    className?: string;
}

const BIMViewer: React.FC<BIMViewerProps> = ({ selectedModel, className = '' }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const componentsRef = useRef<OBC.Components | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [loadingMessage, setLoadingMessage] = useState('');
    const [error, setError] = useState<string>('');
    const [isInitialized, setIsInitialized] = useState(false);

    // Initialize the 3D viewer once
    useEffect(() => {
        if (!containerRef.current || isInitialized) return;

        const initViewer = async () => {
            try {
                setIsLoading(true);
                setLoadingMessage('Setting up 3D world...');

                // Create components instance
                const components = new OBC.Components();
                componentsRef.current = components;

                // Set up the world
                const worlds = components.get(OBC.Worlds);
                const world = worlds.create<
                    OBC.SimpleScene,
                    OBC.SimpleCamera,
                    OBC.SimpleRenderer
                >();

                // Initialize scene, renderer, and camera
                world.scene = new OBC.SimpleScene(components);
                world.renderer = new OBC.SimpleRenderer(components, containerRef.current!);
                world.camera = new OBC.SimpleCamera(components);

                await components.init();

                // Set up the scene with lights
                world.scene.setup();

                // Set light blue background as requested
                world.scene.three.background = new THREE.Color('#E6F3FF');

                setLoadingMessage('Initializing IFC loader...');

                // Set up fragments manager for IFC loading
                const fragments = components.get(OBC.FragmentsManager);

                // Initialize fragments manager with worker
                const githubUrl = "https://thatopen.github.io/engine_fragment/resources/worker.mjs";
                const fetchedUrl = await fetch(githubUrl);
                const workerBlob = await fetchedUrl.blob();
                const workerFile = new File([workerBlob], "worker.mjs", {
                    type: "text/javascript",
                });
                const workerUrl = URL.createObjectURL(workerFile);
                fragments.init(workerUrl);

                // Set up camera controls
                world.camera.controls.addEventListener("rest", () =>
                    fragments.core.update(true)
                );

                // Handle model loading
                fragments.list.onItemSet.add(({ value: model }) => {
                    model.useCamera(world.camera.three);
                    world.scene.three.add(model.object);
                    fragments.core.update(true);
                });

                // Set up IFC loader
                const ifcLoader = components.get(OBC.IfcLoader);
                await ifcLoader.setup({
                    autoSetWasm: false,
                    wasm: {
                        path: "https://unpkg.com/web-ifc@0.0.70/",
                        absolute: true,
                    },
                });

                // Add performance monitoring
                const stats = new Stats();
                stats.showPanel(2);
                stats.dom.style.position = 'absolute';
                stats.dom.style.left = '0px';
                stats.dom.style.top = '0px';
                stats.dom.style.zIndex = '100';
                containerRef.current?.appendChild(stats.dom);

                world.renderer.onBeforeUpdate.add(() => stats.begin());
                world.renderer.onAfterUpdate.add(() => stats.end());

                setIsInitialized(true);
                setIsLoading(false);
                setLoadingMessage('');

            } catch (error) {
                console.error('Error initializing BIM viewer:', error);
                setError('Error initializing BIM viewer');
                setIsLoading(false);
            }
        };

        initViewer();

        // Cleanup function
        return () => {
            if (componentsRef.current) {
                componentsRef.current.dispose();
            }
        };
    }, [isInitialized]);

    // Load model when selectedModel changes
    useEffect(() => {
        if (!selectedModel || !isInitialized || !componentsRef.current) return;

        const loadModel = async () => {
            try {
                setIsLoading(true);
                setError('');
                setLoadingMessage('Fetching IFC model...');

                const components = componentsRef.current!;
                const fragments = components.get(OBC.FragmentsManager);
                const ifcLoader = components.get(OBC.IfcLoader);
                const worlds = components.get(OBC.Worlds);
                const world = worlds.list.values().next().value;

                if (!world) {
                    throw new Error('No world available for rendering');
                }

                // Clear any existing models
                fragments.list.clear();
                world.scene.three.clear();
                // Re-setup lighting by calling setup on the scene component itself
                if ('setup' in world.scene) {
                    (world.scene as any).setup();
                }

                // Download the IFC file from the API
                const blob = await apiService.downloadIfcFile(selectedModel.id);
                const arrayBuffer = await blob.arrayBuffer();
                const buffer = new Uint8Array(arrayBuffer);

                setLoadingMessage('Processing IFC geometry...');

                const modelName = `${selectedModel.project_name}_${selectedModel.model_name}`;
                await ifcLoader.load(buffer, false, modelName, {
                    processData: {
                        progressCallback: (progress) => {
                            console.log('IFC Loading progress:', progress);
                            if (progress < 100) {
                                setLoadingMessage(`Processing IFC geometry... ${Math.round(progress)}%`);
                            }
                        },
                    },
                });

                setLoadingMessage('Finalizing view...');

                // Set camera to look at the model
                if (world.camera && world.camera.controls) {
                    await world.camera.controls.setLookAt(10, 10, 10, 0, 0, 0);
                }
                await fragments.core.update(true);

                setIsLoading(false);
                setLoadingMessage('');

            } catch (error) {
                console.error('Error loading IFC model:', error);
                setError(`Error loading IFC model: ${error instanceof Error ? error.message : 'Unknown error'}`);
                setIsLoading(false);
            }
        };

        loadModel();
    }, [selectedModel, isInitialized]);

    if (!selectedModel) {
        return (
            <div className={`relative w-full h-full ${className} bg-gray-100 flex items-center justify-center`}>
                <div className="text-center text-gray-500">
                    <div className="mb-4">
                        <svg className="mx-auto h-16 w-16 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-medium text-gray-900 mb-2">No Model Selected</h3>
                    <p className="text-gray-600">
                        Please select a project and model to view the BIM model here.
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className={`relative w-full h-full ${className}`}>
            <div
                ref={containerRef}
                className="w-full h-full"
                style={{ background: '#E6F3FF' }}
            />

            {(isLoading || !isInitialized) && (
                <div className="absolute inset-0 bg-slate-50 bg-opacity-90 flex items-center justify-center z-50">
                    <div className="text-center">
                        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
                        <div className="text-lg font-medium text-slate-700 animate-pulse">
                            {loadingMessage || 'Initializing viewer...'}
                        </div>
                    </div>
                </div>
            )}

            {error && (
                <div className="absolute inset-0 bg-red-50 bg-opacity-90 flex items-center justify-center z-50">
                    <div className="text-center">
                        <div className="text-red-600 mb-4">
                            <svg className="mx-auto h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.962-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900 mb-2">Error Loading Model</h3>
                        <p className="text-gray-600 mb-4">{error}</p>
                        <button
                            onClick={() => setError('')}
                            className="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 transition-colors"
                        >
                            Close
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default BIMViewer;
