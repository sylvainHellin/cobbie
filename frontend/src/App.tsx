import { useState, useEffect } from 'react';
import { BIMModel, ChatMessage, LoadingState } from './types';
import { apiService } from './services/api';
import ModelSelector from './components/ModelSelector';
import BIMViewer from './components/BIMViewer';
import ChatInterface from './components/ChatInterface';
import LoadingOverlay from './components/LoadingOverlay';

function App() {
    const [models, setModels] = useState<BIMModel[]>([]);
    const [selectedModel, setSelectedModel] = useState<BIMModel | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [loadingState, setLoadingState] = useState<LoadingState>({
        isLoading: false,
        stage: null,
        message: ''
    });
    const [isModelLoading, setIsModelLoading] = useState(false);

    // Load available models on component mount
    useEffect(() => {
        const loadModels = async () => {
            try {
                setLoadingState({
                    isLoading: true,
                    stage: 'loading',
                    message: 'Loading available models...'
                });
                const modelsData = await apiService.getModels();
                setModels(modelsData);
            } catch (error) {
                console.error('Failed to load models:', error);
            } finally {
                setLoadingState({
                    isLoading: false,
                    stage: null,
                    message: ''
                });
            }
        };

        loadModels();
    }, []);

    const handleModelSelect = (model: BIMModel) => {
        setSelectedModel(model);
        setMessages([]); // Clear chat when switching models
        setIsModelLoading(true);

        // Add welcome message
        const welcomeMessage: ChatMessage = {
            id: Date.now().toString(),
            type: 'assistant',
            content: `Model "${model.model_name}" from project "${model.project_name}" has been loaded. You can now ask questions about this BIM model.`,
            timestamp: new Date()
        };
        setMessages([welcomeMessage]);
    };

    const handleSendMessage = async (question: string) => {
        if (!selectedModel) return;

        // Add user message
        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            type: 'user',
            content: question,
            timestamp: new Date()
        };
        setMessages(prev => [...prev, userMessage]);

        // Set loading state with animated messages
        const loadingStages = [
            { stage: 'loading' as const, message: 'Analyzing your question...' },
            { stage: 'fetching' as const, message: 'Searching BIM model...' },
            { stage: 'processing' as const, message: 'Processing results...' }
        ];

        let currentStage = 0;
        setLoadingState({
            isLoading: true,
            stage: loadingStages[0].stage,
            message: loadingStages[0].message
        });

        // Rotate through loading messages
        const interval = setInterval(() => {
            currentStage = (currentStage + 1) % loadingStages.length;
            setLoadingState(prev => ({
                ...prev,
                stage: loadingStages[currentStage].stage,
                message: loadingStages[currentStage].message
            }));
        }, 3000);

        try {
            const response = await apiService.askQuestion({
                question,
                model_id: selectedModel.id
            });

            clearInterval(interval);

            // Add assistant response
            const assistantMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: response.status === 'success'
                    ? response.answer || 'No answer provided'
                    : `Error: ${response.error_msg}`,
                timestamp: new Date()
            };
            setMessages(prev => [...prev, assistantMessage]);
        } catch (error) {
            clearInterval(interval);
            console.error('Failed to get answer:', error);

            const errorMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: 'Sorry, I encountered an error while processing your question. Please try again.',
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setLoadingState({
                isLoading: false,
                stage: null,
                message: ''
            });
        }
    };

    return (
        <div className="h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex flex-col">
            {/* Header */}
            <header className="bg-white shadow-sm border-b border-slate-200 px-6 py-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-800">IFC Answer Engine</h1>
                        <p className="text-slate-600 text-sm">Ask questions about your BIM models in natural language</p>
                    </div>
                    {selectedModel && (
                        <div className="text-right">
                            <p className="text-sm font-medium text-slate-700">{selectedModel.project_name}</p>
                            <p className="text-xs text-slate-500">{selectedModel.model_name}</p>
                        </div>
                    )}
                </div>
            </header>

            {/* Main Content */}
            <div className="flex-1 flex">
                {!selectedModel ? (
                    <div className="flex-1 flex items-center justify-center">
                        <ModelSelector
                            models={models}
                            onModelSelect={handleModelSelect}
                            isLoading={loadingState.isLoading}
                        />
                    </div>
                ) : (
                    <>
                        {/* BIM Viewer */}
                        <div className="flex-1 relative">
                            <BIMViewer
                                model={selectedModel}
                                onModelLoaded={() => setIsModelLoading(false)}
                                isLoading={isModelLoading}
                            />
                        </div>

                        {/* Chat Interface */}
                        <div className="w-96 border-l border-slate-200 bg-white">
                            <ChatInterface
                                messages={messages}
                                onSendMessage={handleSendMessage}
                                isLoading={loadingState.isLoading}
                                loadingState={loadingState}
                            />
                        </div>
                    </>
                )}
            </div>

            {/* Loading Overlay */}
            {loadingState.isLoading && (
                <LoadingOverlay
                    stage={loadingState.stage}
                    message={loadingState.message}
                />
            )}
        </div>
    );
}

export default App;