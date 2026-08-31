import { Suspense } from "react";
import { AuthPageLayout } from "@/components/auth/AuthPageLayout";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { Spinner } from "@/components/ui/Spinner";

export const metadata = { title: "Reset password · AI Commerce OS" };

export default function ResetPasswordPage() {
  return (
    <AuthPageLayout title="Choose a new password" subtitle="Make it something you'll remember.">
      <Suspense fallback={<Spinner label="Loading..." />}>
        <ResetPasswordForm />
      </Suspense>
    </AuthPageLayout>
  );
}
