import { describe, expect, it } from 'vitest';
import { describeError } from './labels';
import { ApiError } from '@/api/client';

describe('describeError', () => {
  it('uses the operation-specific text for a 404 on ticket status change', () => {
    const message = describeError(new ApiError(404, null), 'PATCH /tickets/{id}/status');

    expect(message).toBe('Заявка не найдена');
  });
});
