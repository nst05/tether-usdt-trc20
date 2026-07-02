const LABELS: Record<string, string> = {
  pending: "Ожидает оплаты",
  confirmed: "Подтверждено",
  paid: "Оплачено",
  declined: "Отклонено",
  cancelled: "Отменено",
  completed: "Завершено",
};

const COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  confirmed: "bg-blue-100 text-blue-700",
  paid: "bg-green-100 text-green-700",
  declined: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-600",
  completed: "bg-purple-100 text-purple-700",
};

export function BookingStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-medium ${COLORS[status] ?? "bg-gray-100 text-gray-600"}`}
    >
      {LABELS[status] ?? status}
    </span>
  );
}
