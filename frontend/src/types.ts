export interface BIMModel {
    id: number;
    project_name: string;
    model_name: string;
    model_description: string;
    model_path: string;
}

export interface ChatMessage {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

export interface QuestionRequest {
    question: string;
    model_id: number;
}

export interface QuestionResponse {
    status: 'success' | 'error';
    answer: string | null;
    error_msg: string | null;
    model_info: {
        id: number;
        project_name: string;
        model_name: string;
        model_description: string;
    } | null;
}

export interface LoadingState {
    isLoading: boolean;
    stage: 'loading' | 'fetching' | 'processing' | null;
    message: string;
}