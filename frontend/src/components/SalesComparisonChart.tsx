import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useI18n } from "../i18n";

export type SalesComparisonPoint = {
  label: string;
  current: number;
  previous: number;
};

type SalesComparisonChartProps = {
  data: SalesComparisonPoint[];
};

export function SalesComparisonChart({ data }: SalesComparisonChartProps) {
  const { t, money } = useI18n();
  const hasData = data.some((point) => point.current > 0 || point.previous > 0);

  if (!hasData) {
    return <div className="empty-state compact">{t("noData")}</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={230}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="salesComparisonFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f97316" stopOpacity={0.32} />
            <stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3e9e3" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#8a766a" }} axisLine={false} tickLine={false} />
        <YAxis hide />
        <Tooltip
          formatter={(value) => money(Number(value))}
          cursor={{ stroke: "#f1ded2", strokeWidth: 1 }}
          contentStyle={{
            borderRadius: 12,
            border: "1px solid #f1ded2",
            fontSize: 12,
            boxShadow: "0 12px 28px rgba(179, 83, 20, .14)",
            padding: "8px 12px",
          }}
        />
        <Legend verticalAlign="top" height={28} iconType="circle" />
        <Line
          type="monotone"
          dataKey="previous"
          name={t("previousPeriod")}
          stroke="#c3c2b7"
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
          activeDot={{ r: 4 }}
        />
        <Area
          type="monotone"
          dataKey="current"
          name={t("currentPeriod")}
          stroke="#f97316"
          strokeWidth={3}
          fill="url(#salesComparisonFill)"
          dot={{ r: 3.5, fill: "#f97316", strokeWidth: 2, stroke: "#fff" }}
          activeDot={{ r: 6, fill: "#f97316", strokeWidth: 2, stroke: "#fff" }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
