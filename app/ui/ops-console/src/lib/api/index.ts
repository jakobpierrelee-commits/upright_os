/**
 * API Client Index
 * Re-exports all domain API clients for convenient imports.
 */

// Shared client utilities
export { BASE, setSessionToken, getSessionToken, authHeaders, fetchJson, postJson } from './client';

// Domain clients
export * from './health';
export * from './control';
export * from './firmware';
export * from './profiles';
export * from './auth';
export * from './telemetry';
