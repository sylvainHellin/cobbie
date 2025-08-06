import React from 'react';
import { BIMModel } from '../types';

interface ModelSelectorProps {
    models: BIMModel[];
    onModelSelect: (model: BIMModel) => void;
    isLoading: boolean;
}

const ModelSelector: React.FC<ModelSelectorProps> = ({ models, onModelSelect, isLoading }) => {
    // Group models by project
    const groupedModels = models.reduce((acc, model) => {
        if (!acc[model.project_name]) {
            acc[model.project_name] = [];
        }
        acc[model.project_name].push(model);
        return acc;
    }, {} as Record<string, BIMModel[]>);

    if (isLoading) {
        return (
            <div className="max-w-2xl mx-auto p-8">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4"></div>
                    <p className="text-slate-600 loading-text">Loading available models...</p>
                </div>
            </div>
        );
    }

    if (models.length === 0) {
        return (
            <div className="max-w-2xl mx-auto p-8">
                <div className="text-center">
                    <div className="w-16 h-16 mx-auto mb-4 bg-slate-200 rounded-full flex items-center justify-center">
                        <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-medium text-slate-900 mb-2">No Models Available</h3>
                    <p className="text-slate-600">No BIM models are currently available. Please check your server configuration.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto p-8">
            <div className="text-center mb-8">
                <h2 className="text-3xl font-bold text-slate-900 mb-2">Select a BIM Model</h2>
                <p className="text-slate-600">Choose a project and model to start asking questions</p>
            </div>

            <div className="space-y-6">
                {Object.entries(groupedModels).map(([projectName, projectModels]) => (
                    <div key={projectName} className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
                        <div className="bg-slate-50 px-6 py-4 border-b border-slate-200">
                            <h3 className="text-lg font-semibold text-slate-800">{projectName}</h3>
                            <p className="text-sm text-slate-600">{projectModels.length} model{projectModels.length !== 1 ? 's' : ''} available</p>
                        </div>

                        <div className="p-6">
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {projectModels.map((model) => (
                                    <button
                                        key={model.id}
                                        onClick={() => onModelSelect(model)}
                                        className="group relative bg-white border border-slate-200 rounded-lg p-4 hover:border-primary-300 hover:shadow-md transition-all duration-200 text-left focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                    >
                                        <div className="flex items-start space-x-3">
                                            <div className="flex-shrink-0">
                                                <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center group-hover:bg-primary-200 transition-colors">
                                                    <svg className="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                                                    </svg>
                                                </div>
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <h4 className="text-sm font-medium text-slate-900 truncate">{model.model_name}</h4>
                                                <p className="text-xs text-slate-500 mt-1 line-clamp-2">{model.model_description}</p>
                                                <div className="mt-2">
                                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800">
                                                        ID: {model.id}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Hover effect */}
                                        <div className="absolute inset-0 rounded-lg bg-primary-50 opacity-0 group-hover:opacity-50 transition-opacity pointer-events-none"></div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ModelSelector;