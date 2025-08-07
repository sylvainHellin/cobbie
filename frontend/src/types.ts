export interface BIMModel {
    id: number;
    project_name: string;
    model_name: string;
    model_description: string;
    model_path: string;
    supabase_url?: string;
}

export interface QuestionRequest {
    question: string;
    model_id: number;
}

export interface QuestionResponse {
    status: 'success' | 'error';
    answer?: string;
    error_msg?: string;
    model_info?: {
        id: number;
        project_name: string;
        model_name: string;
        model_description: string;
    };
}

export interface Project {
    name: string;
    models: BIMModel[];
}

export interface LoadingState {
    stage: 'loading' | 'fetching' | 'processing';
}