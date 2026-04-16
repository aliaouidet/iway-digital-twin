import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="space-y-8 animate-in fade-in max-w-5xl mx-auto">
      <div>
        <h1 class="text-3xl font-bold text-slate-800 tracking-tight">System Configuration</h1>
        <p class="text-slate-500 mt-1">Manage global system parameters, RAG thresholds, and integrations.</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        <!-- Sidebar Navigation -->
        <div class="col-span-1 space-y-2">
           <button *ngFor="let tab of tabs" (click)="activeTab.set(tab.id)"
                   [class]="activeTab() === tab.id ? 'w-full text-left px-5 py-4 rounded-xl bg-white border-l-4 border-indigo-600 shadow-sm font-semibold text-indigo-700 transition-all' : 'w-full text-left px-5 py-4 rounded-xl bg-transparent border-l-4 border-transparent hover:bg-white/60 font-medium text-slate-500 transition-all'">
             <div class="flex items-center gap-3">
               <span class="text-lg" [innerHTML]="tab.icon"></span>
               {{tab.label}}
             </div>
           </button>
        </div>

        <!-- Settings Panels -->
        <div class="col-span-1 lg:col-span-2">
           
           <!-- RAG Tuner Panel -->
           <div *ngIf="activeTab() === 'rag'" class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
             <div class="px-6 py-5 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <h3 class="text-lg font-bold text-slate-800">RAG Engine Configuration</h3>
                  <p class="text-sm text-slate-500">Tune the retrieval augmented generation system.</p>
                </div>
                <button class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition-colors shadow-sm">Save Changes</button>
             </div>
             
             <div class="p-6 space-y-6">
                <!-- Chunking Strategy -->
                <div>
                  <label class="block text-sm font-semibold text-slate-700 mb-1">Document Chunking Strategy</label>
                  <p class="text-xs text-slate-500 mb-3">Define how knowledge base files are split for vector embedding.</p>
                  <select class="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 outline-none transition">
                    <option>Semantic Splitting (Recommended)</option>
                    <option>Fixed Size Overlap (500 tokens)</option>
                    <option>Markdown Header Splitting</option>
                  </select>
                </div>

                <div class="grid grid-cols-2 gap-6">
                   <!-- Top K -->
                   <div>
                     <label class="block text-sm font-semibold text-slate-700 mb-1">Retrieval (Top K)</label>
                     <p class="text-xs text-slate-500 mb-3">Number of chunks to inject into prompt.</p>
                     <input type="number" value="3" class="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 outline-none transition">
                   </div>
                   
                   <!-- Similarity Threshold -->
                   <div>
                     <label class="block text-sm font-semibold text-slate-700 mb-1">Similarity Threshold (%)</label>
                     <p class="text-xs text-slate-500 mb-3">Minimum cosine similarity required.</p>
                     <input type="number" value="82" class="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 outline-none transition">
                   </div>
                </div>

                <hr class="border-slate-100">

                <!-- Escalation Policy -->
                <div>
                   <h4 class="text-sm font-semibold text-slate-800 mb-4">Fallback & Escalation Workflow</h4>
                   
                   <label class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 bg-slate-50 cursor-pointer hover:border-indigo-300 transition-colors">
                     <input type="checkbox" checked class="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500">
                     <div class="flex-1">
                       <div class="text-sm font-semibold text-slate-700">Enable Generative AI Fallback</div>
                       <div class="text-xs text-slate-500">If RAG fails to find highly similar chunks, allow the LLM to use its parametric knowledge with a strict system prompt.</div>
                     </div>
                   </label>
                   
                   <label class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 mt-3 hover:border-indigo-300 transition-colors cursor-pointer">
                     <input type="checkbox" checked class="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500">
                     <div class="flex-1">
                       <div class="text-sm font-semibold text-slate-700">Auto-Escalate Negative Sentiment</div>
                       <div class="text-xs text-slate-500">Route directly to human queue if user message sentiment score is severely negative.</div>
                     </div>
                   </label>
                </div>
             </div>
           </div>

           <!-- LLM Tuner Panel -->
           <div *ngIf="activeTab() === 'llm'" class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
             <!-- ... content for llm ... -->
             <div class="px-6 py-5 border-b border-slate-100">
                <h3 class="text-lg font-bold text-slate-800">Language Model Settings</h3>
             </div>
             <div class="p-6 space-y-6">
                <div>
                  <label class="block text-sm font-semibold text-slate-700 mb-1">Primary Model</label>
                  <select class="w-full py-2.5 px-4 rounded-lg border border-slate-200 bg-slate-50 text-sm">
                    <option>GPT-4o (OpenAI)</option>
                    <option>Claude 3.5 Sonnet (Anthropic)</option>
                    <option>Gemini 1.5 Pro (Google)</option>
                  </select>
                </div>
                
                <div>
                   <label class="block text-sm font-semibold text-slate-700 mb-1 flex justify-between">
                     System Prompt configuration
                     <button class="text-xs text-indigo-600 hover:text-indigo-800 underline">View Variables</button>
                   </label>
                   <textarea rows="8" class="w-full p-4 text-sm font-mono bg-slate-900 leading-relaxed text-indigo-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none resize-y">You are a highly capable AI Support Assistant for the I-Way platform.

Rules:
1. ONLY use information provided in the Context block.
2. If the answer is not in the context, explicitly state "I don't have enough context, escalating to human."
3. Maintain a professional, concise tone.

Context: {{ "{{" }}rag_context{{ "}}" }}
User: {{ "{{" }}user_query{{ "}}" }}
</textarea>
                </div>
                
                <div class="flex items-center gap-4">
                  <div class="flex-1">
                     <label class="block text-sm font-semibold text-slate-700 mb-1">Temperature</label>
                     <input type="range" class="w-full accent-indigo-600" min="0" max="1" step="0.1" value="0.2">
                  </div>
                  <div class="w-16 text-center mt-6 text-sm font-bold text-indigo-600 bg-indigo-50 py-1 rounded">0.2</div>
                </div>
             </div>
           </div>

           <!-- Data Sources -->
           <div *ngIf="activeTab() === 'data'" class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
              <div class="px-6 py-5 border-b border-slate-100 flex justify-between items-center">
                 <h3 class="text-lg font-bold text-slate-800">Knowledge Integrations</h3>
                 <button class="text-sm font-semibold text-indigo-600 hover:text-indigo-800">+ Add Source</button>
              </div>
              <div class="p-6">
                 <div class="space-y-4">
                   <!-- Source Item -->
                   <div class="flex items-center justify-between p-4 border border-slate-200 rounded-xl hover:border-indigo-300 transition-colors">
                     <div class="flex items-center gap-4">
                       <div class="w-10 h-10 bg-[#FF9900]/10 text-[#FF9900] rounded-lg flex items-center justify-center font-bold text-xl">S3</div>
                       <div>
                         <div class="font-bold text-slate-800 text-sm">AWS S3 Bucket (Help Center)</div>
                         <div class="text-xs text-slate-500 mt-0.5">Last synced: 2 hours ago • 14,021 documents</div>
                       </div>
                     </div>
                     <div class="flex items-center gap-3">
                       <span class="px-2 py-1 bg-emerald-100 text-emerald-700 rounded text-xs font-semibold">Active</span>
                       <button class="p-2 hover:bg-slate-100 rounded text-slate-400">•••</button>
                     </div>
                   </div>
                   
                   <div class="flex items-center justify-between p-4 border border-slate-200 rounded-xl hover:border-indigo-300 transition-colors">
                     <div class="flex items-center gap-4">
                       <div class="w-10 h-10 bg-blue-500/10 text-blue-600 rounded-lg flex items-center justify-center font-bold text-xl">C</div>
                       <div>
                         <div class="font-bold text-slate-800 text-sm">Confluence Space (Internal)</div>
                         <div class="text-xs text-slate-500 mt-0.5">Last synced: 1 day ago • 3,401 documents</div>
                       </div>
                     </div>
                     <div class="flex items-center gap-3">
                       <span class="px-2 py-1 bg-emerald-100 text-emerald-700 rounded text-xs font-semibold">Active</span>
                       <button class="p-2 hover:bg-slate-100 rounded text-slate-400">•••</button>
                     </div>
                   </div>
                 </div>
              </div>
           </div>

        </div>
      </div>
    </div>
  `
})
export class AdminComponent {
  tabs = [
    { id: 'rag', label: 'RAG Pipeline', icon: '🧠' },
    { id: 'llm', label: 'LLM Tuner', icon: '🤖' },
    { id: 'data', label: 'Data Sources', icon: '📚' },
    { id: 'api', label: 'API Keys', icon: '🔑' }
  ];
  
  activeTab = signal('rag');
}
