import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'playwright-report', 'test-results'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        {
          allowConstantExport: true,
          allowExportNames: [
            'buttonVariants',
            'badgeVariants',
            'describedBy',
            'VERIFICATION_STATUSES',
            'VERIFICATION_STATUS_META',
            'POLLING_UNIT_STATUS_META',
            'UPDATE_CATEGORY_LABEL',
            'UPDATE_VERIFICATION_META',
            'DEMO_RESULT_LABEL',
            'NIGERIA_LOGO_PATH',
            'NIGERIA_MAP_PATH',
            'FINGERPRINT_RIDGES',
            'NIGERIA_STATES',
            'DottedNigeria',
            'NigeriaMark',
            'LogoMark',
            'dataStatusLabel',
            'isOfficialNotice',
            'displayStatus',
            'formatDateTime',
            'formatDate',
            'formatCoordinates',
            'EVIDENCE_STATUS_META',
            'REVIEW_REASON_LABELS',
            'confidenceTone',
            'formatConfidence',
            'reviewReasonLabel',
          ],
        },
      ],
    },
  },
)
