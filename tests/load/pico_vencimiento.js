// Prueba de carga con k6 que simula el pico del día de vencimiento sobre los endpoints públicos.
// Uso: k6 run -e BASE_URL=https://tramites.ejemplo.gob.pe tests/load/pico_vencimiento.js
// Mientras corre: kubectl -n tramites get hpa -w   (los servicios deben escalar sin errores)
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },   // día normal
    { duration: '3m', target: 1000 },  // inicio del pico
    { duration: '10m', target: 1000 }, // pico sostenido
    { duration: '2m', target: 0 },
  ],
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<800'] },
};
const BASE = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  const d = Math.floor(Math.random() * 10);
  const r1 = http.get(`${BASE}/api/alertas/calendario/${d}`);
  check(r1, { 'calendario 200': (r) => r.status === 200 });
  const r2 = http.post(`${BASE}/api/simulador/multa`,
    JSON.stringify({ tributo_omitido: 500 + Math.random() * 3000, dias_retraso: Math.floor(Math.random() * 90) }),
    { headers: { 'Content-Type': 'application/json' } });
  check(r2, { 'simulador 200': (r) => r.status === 200 });
  sleep(1);
}
