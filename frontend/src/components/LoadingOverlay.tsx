import React from 'react';
import { LoadingState } from '../types';

interface LoadingOverlayProps {
    stage: LoadingState['stage'];
    message: string;
}

const LoadingOverlay: React.FC<LoadingOverlayProps> = ({ stage, message }) => {
    const getStageIcon = () => {
        switch (stage) {
            case 'loading':
                return (
                    <svg className="w-8 h-8 text-primary-600 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                );
            case 'fetching':
                return (
                    <svg className="w-8 h-8 text-primary-600 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                );
            case 'processing':
                return (
                    <svg className="w-8 h-8 text-primary-600 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                );
            default:
                return (
                    <svg className="w-8 h-8 text-primary-600 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                );
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-20 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-8 shadow-xl max-w-sm mx-4">
                <div className="text-center">
                    {/* Animated Icon */}
                    <div className="flex justify-center mb-4">
                        <div className="p-3 bg-primary-50 rounded-full">
                            {getStageIcon()}
                        </div>
                    </div>

                    {/* Loading Message */}
                    <h3 className="text-lg font-semibold text-slate-800 mb-2 loading-text">
                        {message}
                    </h3>

                    {/* Stage Indicator */}
                    <div className="flex justify-center space-x-2 mb-4">
                        <div className={`w-2 h-2 rounded-full transition-colors ${stage === 'loading' ? 'bg-primary-600' : 'bg-slate-300'}`} />
                        <div className={`w-2 h-2 rounded-full transition-colors ${stage === 'fetching' ? 'bg-primary-600' : 'bg-slate-300'}`} />
                        <div className={`w-2 h-2 rounded-full transition-colors ${stage === 'processing' ? 'bg-primary-600' : 'bg-slate-300'}`} />
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-slate-200 rounded-full h-1">
                        <div
                            className="bg-gradient-to-r from-primary-500 to-primary-600 h-1 rounded-full transition-all duration-1000 ease-out shimmer-effect"
                            style={{
                                width: stage === 'loading' ? '33%' : stage === 'fetching' ? '66%' : '99%'
                            }}
                        />
                    </div>

                    <p className="text-sm text-slate-500 mt-3">
                        Please wait while we process your request...
                    </p>
                </div>
            </div>
        </div>
    );
};

export default LoadingOverlay;