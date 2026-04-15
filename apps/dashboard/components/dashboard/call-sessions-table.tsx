import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type CallSessionRow = {
  id: string;
  eventTitle: string;
  eventDate: string | null;
  attendees: number;
  declines: number;
  feedbacks: number;
  avgRating: number | null;
};

export function CallSessionsTable({ rows }: { rows: CallSessionRow[] }) {
  return (
    <ScrollArea className="w-full">
      <div className="min-w-[760px]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Созвон</TableHead>
              <TableHead>Дата</TableHead>
              <TableHead>Зашли</TableHead>
              <TableHead>Отказались</TableHead>
              <TableHead>Отзывы</TableHead>
              <TableHead>Средняя оценка</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                  По текущим фильтрам пока нет данных по созвонам.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-medium text-foreground">{row.eventTitle}</TableCell>
                  <TableCell>{row.eventDate ?? "—"}</TableCell>
                  <TableCell>{row.attendees}</TableCell>
                  <TableCell>{row.declines}</TableCell>
                  <TableCell>{row.feedbacks}</TableCell>
                  <TableCell>{row.avgRating == null ? "—" : row.avgRating}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </ScrollArea>
  );
}
