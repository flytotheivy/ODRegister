import type {Locale} from './i18n';
/* EDS-03 기관 계획 화면 문구. 세르비아어 2종은 Claude 번역 → 원어민 검수 필요 */
const en={
 progress:'Progress',stepEnter:'Enter datasets',stepReview:'Review',stepDone:'Submitted',stepAmendDone:'Changes saved',
 institution:'Institution',planStatus:'Plan status',window:'Registration',
 guideTitle:'What to enter',
 guideRequired:'Required for every dataset: title and EU Data Theme.',
 guideOptional:'Optional: description, responsible department and planned quarter.',
 guidePrivacy:'Confirm that each dataset and its description contain no personal data. Changing a dataset removes the confirmation.',
 guideSave:'You can save a draft at any time. After review, submission makes the plan public immediately.',
 guideAmend:'The public plan stays unchanged until you review and save the full amendment.',
 guideOne:'One plan per institution and year.',
 actions:'Actions',
};
type Messages={[K in keyof typeof en]:string};
export const planMessages:Record<Locale,Messages>={en,
 'sr-Latn':{
 progress:'Napredak',stepEnter:'Unos skupova podataka',stepReview:'Pregled',stepDone:'Podneto',stepAmendDone:'Izmene sačuvane',
 institution:'Institucija',planStatus:'Status plana',window:'Prijava',
 guideTitle:'Šta treba uneti',
 guideRequired:'Obavezno za svaki skup podataka: naziv i EU tema podataka.',
 guideOptional:'Opciono: opis, nadležno odeljenje i planirani kvartal.',
 guidePrivacy:'Potvrdite da skup podataka i njegov opis ne sadrže podatke o ličnosti. Izmena skupa podataka poništava potvrdu.',
 guideSave:'Nacrt možete sačuvati u bilo kom trenutku. Posle pregleda, podnošenjem plan odmah postaje javan.',
 guideAmend:'Javni plan ostaje nepromenjen dok ne pregledate i sačuvate celu izmenu.',
 guideOne:'Jedan plan po instituciji i godini.',
 actions:'Radnje',
 },
 'sr-Cyrl':{
 progress:'Напредак',stepEnter:'Унос скупова података',stepReview:'Преглед',stepDone:'Поднето',stepAmendDone:'Измене сачуване',
 institution:'Институција',planStatus:'Статус плана',window:'Пријава',
 guideTitle:'Шта треба унети',
 guideRequired:'Обавезно за сваки скуп података: назив и ЕУ тема података.',
 guideOptional:'Опционо: опис, надлежно одељење и планирани квартал.',
 guidePrivacy:'Потврдите да скуп података и његов опис не садрже податке о личности. Измена скупа података поништава потврду.',
 guideSave:'Нацрт можете сачувати у било ком тренутку. После прегледа, подношењем план одмах постаје јаван.',
 guideAmend:'Јавни план остаје непромењен док не прегледате и сачувате целу измену.',
 guideOne:'Један план по институцији и години.',
 actions:'Радње',
 }};
