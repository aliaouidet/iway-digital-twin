import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { MetricsService } from './metrics.service';
import { environment } from '../../../environments/environment';

describe('MetricsService', () => {
  let svc: MetricsService;
  let http: HttpTestingController;
  const base = `${environment.apiUrl}/api/v1`;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule], providers: [MetricsService] });
    svc = TestBed.inject(MetricsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('getMetrics forwards date params', () => {
    svc.getMetrics('2026-06-01', '2026-06-07').subscribe();
    const req = http.expectOne(r => r.url === `${base}/metrics`);
    expect(req.request.params.get('start_date')).toBe('2026-06-01');
    expect(req.request.params.get('end_date')).toBe('2026-06-07');
    req.flush({});
  });

  it('getMetrics omits params when no dates', () => {
    svc.getMetrics().subscribe();
    const req = http.expectOne(`${base}/metrics`);
    expect(req.request.params.has('start_date')).toBe(false);
    req.flush({});
  });

  it('getFeedbackStats calls /feedback/stats', () => {
    let got: any;
    svc.getFeedbackStats().subscribe(r => (got = r));
    http.expectOne(`${base}/feedback/stats`).flush({ total: 5, positive: 4, negative: 1, csat_score: 80 });
    expect(got.csat_score).toBe(80);
  });

  it('getOpsMetrics calls /monitoring/ops', () => {
    svc.getOpsMetrics().subscribe();
    const req = http.expectOne(`${base}/monitoring/ops`);
    expect(req.request.method).toBe('GET');
    req.flush({});
  });

  it('getHourlyTraffic forwards the date', () => {
    svc.getHourlyTraffic('2026-06-14').subscribe();
    const req = http.expectOne(r => r.url === `${base}/metrics/traffic`);
    expect(req.request.params.get('date')).toBe('2026-06-14');
    req.flush({ hourly: [], date: '2026-06-14' });
  });
});
