'use client';

import dynamic from 'next/dynamic';

/** apexcharts touches `window` at import time — load it only in the browser. */
const ApexChart = dynamic(() => import('react-apexcharts'), {
  ssr: false,
  loading: () => <div className="h-[260px] w-full animate-pulse rounded-sm bg-elevated" />,
});

export default ApexChart;
