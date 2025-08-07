import React, { useState, useEffect } from 'react';
import { BIMModel, Project } from '../types';
import { apiService } from '../services/api';

interface ModelSelectorProps {
    onModelSelected: (model: BIMModel) => void;
    className?: string;
}

const ModelSelector: React.FC<ModelSelectorProps> = ({ onModelSelected, className = '' }) => {
    const [projects, setProjects] = useState<Project[]>([]);
    const [selectedProject, setSelectedProject] = useState<string>('');
    const [selectedModel, setSelectedModel] = useState<BIMModel | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string>('');

    useEffect(() => {
        loadModels();
    }, []);

    const loadModels = async () => {
        try {
            setIsLoading(true);
            setError('');
            const models = await apiService.getModels();

            // Group models by project
            const projectMap = new Map<string, BIMModel[]>();
            models.forEach(model => {
                if (!projectMap.has(model.project_name)) {
                    projectMap.set(model.project_name, []);
                }
                projectMap.get(model.project_name)!.push(model);
            });

            const projectsList: Project[] = Array.from(projectMap.entries()).map(([name, models]) => ({
                name,
                models
            }));

            setProjects(projectsList);
        } catch (err) {
            console.error('Error loading models:', err);
            setError('Failed to load available models. Please check if the API server is running.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleProjectChange = (projectName: string) => {
        setSelectedProject(projectName);
        setSelectedModel(null);
    };

    const handleModelSelect = (model: BIMModel) => {
        setSelectedModel(model);
        onModelSelected(model);
    };

    const currentProject = projects.find(p => p.name === selectedProject);

    if (isLoading) {
        return (
            <div className={`bg-white rounded-lg shadow-sm p-6 ${className}`}>
                <div className="flex items-center justify-center">
                    <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mr-3"></div>
                    <span className="text-gray-600">Loading available models...</span>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={`bg-white rounded-lg shadow-sm p-6 ${className}`}>
                <div className="text-center">
                    <div className="text-red-600 mb-4">
                        <svg className="mx-auto h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.962-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-medium text-gray-900 mb-2">Connection Error</h3>
                    <p className="text-gray-600 mb-4">{error}</p>
                    <button
                        onClick={loadModels}
                        className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
                    >
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className={`bg-white rounded-lg shadow-sm p-6 ${className}`}>
            <h2 className="text-xl font-semibold text-gray-800 mb-6">Select BIM Model</h2>

            {/* Project Selection */}
            <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                    Project
                </label>
                <select
                    value={selectedProject}
                    onChange={(e) => handleProjectChange(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                    <option value="">Select a project...</option>
                    {projects.map((project) => (
                        <option key={project.name} value={project.name}>
                            {project.name} ({project.models.length} model{project.models.length !== 1 ? 's' : ''})
                        </option>
                    ))}
                </select>
            </div>

            {/* Model Selection */}
            {selectedProject && currentProject && (
                <div className="mb-6">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Model
                    </label>
                    <div className="space-y-2">
                        {currentProject.models.map((model) => (
                            <div
                                key={model.id}
                                className={`p-4 border rounded-lg cursor-pointer transition-colors ${selectedModel?.id === model.id
                                        ? 'border-blue-500 bg-blue-50'
                                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                                    }`}
                                onClick={() => handleModelSelect(model)}
                            >
                                <div className="flex justify-between items-start">
                                    <div className="flex-1">
                                        <h3 className="font-medium text-gray-900">{model.model_name}</h3>
                                        {model.model_description && (
                                            <p className="text-sm text-gray-600 mt-1">{model.model_description}</p>
                                        )}
                                    </div>
                                    <div className="ml-4">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                                            ID: {model.id}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {selectedModel && (
                <div className="bg-green-50 border border-green-200 rounded-md p-4">
                    <div className="flex">
                        <div className="flex-shrink-0">
                            <svg className="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                        </div>
                        <div className="ml-3">
                            <h3 className="text-sm font-medium text-green-800">Model Selected</h3>
                            <div className="text-sm text-green-700 mt-1">
                                <p><strong>{selectedModel.model_name}</strong> from project <strong>{selectedModel.project_name}</strong></p>
                                <p className="text-xs mt-1">The BIM viewer will now load this model...</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ModelSelector;