import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';


export interface AgentMessage {
  type: string;
  content: string;
}

export interface AgentResponse {
  result: string;
  messages: AgentMessage[];
}

@Injectable({
  providedIn: 'root'
})
export class AgentService {
  private http = inject(HttpClient);
  
  // Uses relative path because FastAPI serves both frontend and backend in production
  // In development, this relies on proxy or CORS
  private apiUrl = '/api/v1/execute';

  executePrompt(prompt: string): Observable<AgentResponse> {
    return this.http.post<AgentResponse>(this.apiUrl, { prompt });
  }
}
