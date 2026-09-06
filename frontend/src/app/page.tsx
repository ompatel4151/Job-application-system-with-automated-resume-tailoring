import { KanbanBoard } from "@/components/board/kanban-board";
import { NewApplicationDialog } from "@/components/new-application-dialog";

export default function Home() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Pipeline</h1>
          <p className="text-sm text-muted-foreground">
            Drag a card between stages to update its status.
          </p>
        </div>
        <NewApplicationDialog />
      </div>
      <KanbanBoard />
    </div>
  );
}
