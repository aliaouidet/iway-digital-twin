import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { LogsService } from './logs.service';
import { environment } from '../../../environments/environment';

describe('LogsService', () => {
  let svc: LogsService;
  let http: HttpTestingController;
  const base = `${environment.apiUrl}/api/v1`;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule], providers: [LogsService] });
    svc = TestBed.inject(LogsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('serializes all filters incl. dates and scales similarity to 0-1', () => {
    svc.getLogs({
      page: 1, page_size: 20, outcome: 'RAG_RESOLVED',
      min_similarity: 80, start_date: '2026-06-01', end_date: '2026-06-07',
    }).subscribe();
    const req = http.expectOne(r => r.url === `${base}/logs`);
    const p = req.request.params;
    expect(p.get('outcome')).toBe('RAG_RESOLVED');
    expect(p.get('min_similarity')).toBe('0.8');     // 80% → 0.8
    expect(p.get('start_date')).toBe('2026-06-01');
    expect(p.get('end_date')).toBe('2026-06-07');
    req.flush({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 });
  });

  it('sends a bare request when no filters', () => {
    svc.getLogs().subscribe();
    const req = http.expectOne(`${base}/logs`);
    expect(req.request.params.keys().length).toBe(0);
    req.flush({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 });
  });
});
