import { useState } from 'react';
import BIMViewer from './components/BIMViewer';
import ModelSelector from './components/ModelSelector';
import { BIMModel } from './types';

function App() {
    const [selectedModel, setSelectedModel] = useState<BIMModel | null>(null);

    return (
        <div className="w-screen h-screen flex flex-col bg-gray-50">
            <header className="bg-white shadow-sm border-b border-gray-200 p-4">
                <h1 className="text-2xl font-bold text-gray-800">IFC Answer Engine</h1>
                <p className="text-gray-600 mt-1">
                    {selectedModel
                        ? `Viewing: ${selectedModel.project_name} - ${selectedModel.model_name}`
                        : 'Select a BIM model to get started'
                    }
                </p>
            </header>

            <div className="flex-1 flex">
                {/* BIM Viewer - Left side */}
                <div className="flex-1 bg-white">
                    <BIMViewer selectedModel={selectedModel || undefined} className="w-full h-full" />
                </div>

                {/* Right side panel */}
                <div className="w-96 bg-gray-50 border-l border-gray-200 flex flex-col">
                    {/* Model Selection */}
                    <div className="p-4">
                        <ModelSelector
                            onModelSelected={setSelectedModel}
                            className="w-full"
                        />
                    </div>

                    {/* Chat Interface (placeholder for now) */}
                    {selectedModel && (
                        <div className="flex-1 p-4 pt-0">
                            <div className="bg-white rounded-lg p-4 shadow-sm h-full">
                                <h2 className="text-lg font-semibold text-gray-800 mb-4">Chat Interface</h2>
                                <p className="text-gray-600 text-sm">
                                    Chat interface will be implemented here according to the requirements.
                                    You can now ask questions about the selected model:
                                    <span className="font-medium text-gray-800">
                                        {selectedModel.model_name}
                                    </span>
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default App;