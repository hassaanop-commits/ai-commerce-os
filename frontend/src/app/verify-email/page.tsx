import { Suspense } from "react";
import { AuthPageLayout } from "@/components/auth/AuthPageLayout";
import { VerifyEmailStatus } from "@/components/auth/VerifyEmailStatus";
import { Spinner } from "@/components/ui/Spinner";

export const metadata = { title: "Verify your email · AI Commerce OS" };

export default function VerifyEmailPage() {
  return (
    <AuthPageLayout title="Verify your email">
      <Suspense fallback={<Spinner label="Loading..." />}>
        <VerifyEmailStatus />
      </Suspense>
    </AuthPageLayout>
  );
}
