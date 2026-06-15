import { TestBed } from '@angular/core/testing';
import { ToastService } from './toast.service';

describe('ToastService', () => {
  let svc: ToastService;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [ToastService] });
    svc = TestBed.inject(ToastService);
  });

  it('show() appends a toast', () => {
    svc.show('hello', 'success', 100000);
    expect(svc.toasts().length).toBe(1);
    expect(svc.toasts()[0].type).toBe('success');
  });

  it('caps visible toasts at 5', () => {
    for (let i = 0; i < 7; i++) svc.show('m' + i, 'info', 100000);
    expect(svc.toasts().length).toBe(5);
    // keeps the most recent
    expect(svc.toasts()[4].message).toBe('m6');
  });

  it('dismiss() removes by id', () => {
    svc.show('x', 'error', 100000);
    const id = svc.toasts()[0].id;
    svc.dismiss(id);
    expect(svc.toasts().length).toBe(0);
  });
});
