import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage, LoadingState } from '../types';

interface ChatInterfaceProps {
    messages: ChatMessage[];
    onSendMessage: (message: string) => void;
    isLoading: boolean;
    loadingState: LoadingState;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({
    messages,
    onSendMessage,
    isLoading,
    loadingState
}) => {
    const [inputValue, setInputValue] = useState('');
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Auto-scroll to bottom when new messages arrive
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isLoading]);

    // Focus input on mount
    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (inputValue.trim() && !isLoading) {
            onSendMessage(inputValue.trim());
            setInputValue('');
        }
    };

    const formatTimestamp = (date: Date) => {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className="flex flex-col h-full">
            {/* Chat Header */}
            <div className="bg-slate-50 border-b border-slate-200 px-4 py-3">
                <h3 className="font-semibold text-slate-800">Ask Questions</h3>
                <p className="text-xs text-slate-600">Query your BIM model in natural language</p>
            </div>

            {/* Messages Container */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.length === 0 && !isLoading && (
                    <div className="text-center py-8">
                        <div className="w-16 h-16 mx-auto mb-4 bg-primary-100 rounded-full flex items-center justify-center">
                            <svg className="w-8 h-8 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                            </svg>
                        </div>
                        <p className="text-slate-500 text-sm">Start a conversation about your BIM model</p>
                        <div className="mt-4 space-y-2 text-xs text-slate-400">
                            <p>Try asking questions like:</p>
                            <ul className="space-y-1">
                                <li>"What is the height of the living room?"</li>
                                <li>"How many doors are in this building?"</li>
                                <li>"What materials are used for the walls?"</li>
                            </ul>
                        </div>
                    </div>
                )}

                {messages.map((message) => (
                    <div
                        key={message.id}
                        className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${message.type === 'user'
                                    ? 'bg-primary-600 text-white'
                                    : 'bg-slate-100 text-slate-800'
                                }`}
                        >
                            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                            <p
                                className={`text-xs mt-1 ${message.type === 'user' ? 'text-primary-200' : 'text-slate-500'
                                    }`}
                            >
                                {formatTimestamp(message.timestamp)}
                            </p>
                        </div>
                    </div>
                ))}

                {/* Loading Message */}
                {isLoading && (
                    <div className="flex justify-start">
                        <div className="max-w-xs lg:max-w-md px-4 py-2 bg-slate-100 rounded-lg">
                            <div className="flex items-center space-x-2">
                                <div className="flex space-x-1">
                                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></div>
                                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                                </div>
                                <span className="text-sm text-slate-600 loading-text">
                                    {loadingState.message}
                                </span>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input Form */}
            <div className="border-t border-slate-200 p-4">
                <form onSubmit={handleSubmit} className="flex space-x-2">
                    <input
                        ref={inputRef}
                        type="text"
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        placeholder="Ask a question about your BIM model..."
                        disabled={isLoading}
                        className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-slate-100 disabled:text-slate-500 text-sm"
                    />
                    <button
                        type="submit"
                        disabled={!inputValue.trim() || isLoading}
                        className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {isLoading ? (
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        ) : (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                            </svg>
                        )}
                    </button>
                </form>

                {/* Quick Suggestions */}
                {messages.length === 0 && !isLoading && (
                    <div className="mt-3 flex flex-wrap gap-2">
                        {[
                            "How many rooms are there?",
                            "What is the total floor area?",
                            "List all the materials used"
                        ].map((suggestion) => (
                            <button
                                key={suggestion}
                                onClick={() => {
                                    setInputValue(suggestion);
                                    inputRef.current?.focus();
                                }}
                                className="px-3 py-1 text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full transition-colors"
                            >
                                {suggestion}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ChatInterface;