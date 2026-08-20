import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { READ_ONLY_HINT, useDemoMode } from "@/lib/demo"
import type { Investigation } from "@/lib/types"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"

export function NewInvestigationDialog() {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState("")
  const [hypothesis, setHypothesis] = useState("")
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { writesLocked: demo } = useDemoMode()

  const mutation = useMutation({
    mutationFn: () =>
      api.post<Investigation>("/api/investigations", {
        question,
        hypothesis: hypothesis || undefined,
      }),
    onSuccess: (inv) => {
      queryClient.invalidateQueries({ queryKey: ["investigations"] })
      setOpen(false)
      setQuestion("")
      setHypothesis("")
      navigate({ to: "/app/investigations/$investigationId", params: { investigationId: inv.id } })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {/* ponytail: this codebase's shadcn/dialog is Base UI, not Radix — use its
          render prop instead of the brief's Radix-style `asChild` (see DialogClose
          usage in dialog.tsx for the same convention). */}
      <DialogTrigger
        render={
          <Button disabled={demo} title={demo ? READ_ONLY_HINT : undefined}>
            New investigation
          </Button>
        }
      />
      <DialogContent className="border border-border bg-white/[0.03] bg-popover">
        <DialogHeader>
          <DialogTitle className="font-light tracking-tight">New investigation</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label
              htmlFor="question"
              className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"
            >
              Question
            </Label>
            <Textarea
              id="question"
              value={question}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What do you want to investigate?"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label
              htmlFor="hypothesis"
              className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"
            >
              Hypothesis (optional)
            </Label>
            <Input
              id="hypothesis"
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!question.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Running…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
