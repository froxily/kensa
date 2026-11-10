import { test } from 'node:test';
import { endpoint } from '../src/settings.js';
test('endpoint is configured', () => endpoint());
// The endpoint is supplied by the job.
