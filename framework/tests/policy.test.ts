import { describe, it, expect } from 'vitest';
import { canReadLab } from '../app/authorization.js';
describe('REQ-ISOLATION pure ownership policy', () => {
  it('allows the authenticated owner', () => { expect(canReadLab('patient-a', 'patient-a')).toBe(true); });
  it('denies another patient', () => { expect(canReadLab('patient-a', 'patient-b')).toBe(false); });
  it('denies a missing principal', () => { expect(canReadLab(undefined, 'patient-a')).toBe(false); });
});
