export const en = {
  brand: 'Serbia Open Data', preview: 'Development preview', language: 'Language',
  eyebrow: 'Annual publication planning', title: 'Open data begins\nwith a plan.',
  introduction: 'A shared place for institutions to prepare their annual open data publication plans.',
  scope: "Institutional access requests and sign-in are available in this prototype. Plan submission and public browsing will follow.",
  statusHeading: 'Connection check', statusIntro: 'Check whether this preview can reach its supporting services.',
  loading: 'Checking connection…', ready: 'Connection ready', unavailable: 'Connection unavailable',
  readyHint: 'The application and its database are responding.',
  unavailableHint: 'A supporting service could not be reached. Please try again.',
  invalidHint: 'The service returned an unexpected response. Please try again.',
  timeoutHint: 'The connection check took too long. Please try again.',
  api: 'Application service', database: 'Database connection', ok: 'Available', unknown: 'Not confirmed',
  refresh: 'Check again', statusLabel: 'Service connection status',
  stepsHeading: 'One annual plan. A clearer path to publication.',
  accessTitle: 'Request access', accessBody: 'Institutional access will be reviewed by an administrator.',
  planTitle: 'Prepare your plan', planBody: 'Describe the datasets your institution intends to publish.',
  publishTitle: 'Share what is planned', publishBody: 'Submitted plans will be available for public browsing.',
  later: 'Later stage', footer: 'Prototype · Synthetic demonstration data only',
  draft: 'Language draft · Review pending', skip: 'Skip to main content',
} as const;
export type MessageKey = keyof typeof en;
export type Messages = { [K in MessageKey]: string };
