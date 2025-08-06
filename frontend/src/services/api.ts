import axios from 'axios';
import { BIMModel, QuestionRequest, QuestionResponse } from '../types';

const API_BASE_URL = 'http://127.0.0.1:8000';

const api = axios.create({
    baseURL: API_BASE_URL,
    timeout: 60000, // 60 seconds timeout for long-running queries
});

export const apiService = {
    // Get all available models
    async getModels(): Promise<BIMModel[]> {
        const response = await api.get<{ models: BIMModel[] }>('/models');
        return response.data.models;
    },

    // Ask a question about a model
    async askQuestion(request: QuestionRequest): Promise<QuestionResponse> {
        const response = await api.post<QuestionResponse>('/ask', request);
        return response.data;
    },

    // Get IFC file URL for a model
    getIfcFileUrl(modelId: number): string {
        return `${API_BASE_URL}/models/${modelId}/ifc`;
    },

    // Download IFC file as blob
    async downloadIfcFile(modelId: number): Promise<Blob> {
        const response = await api.get(`/models/${modelId}/ifc`, {
            responseType: 'blob',
        });
        return response.data;
    },
};