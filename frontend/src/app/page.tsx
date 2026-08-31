import { redirect } from "next/navigation";
import { getCurrentUserServer } from "@/lib/server-api";

export default async function RootPage() {
  const user = await getCurrentUserServer();
  redirect(user ? "/dashboard" : "/login");
}
