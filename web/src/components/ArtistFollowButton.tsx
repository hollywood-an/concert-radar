"use client";

import FollowButton from "@/components/FollowButton";
import { toggleFollow } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

export default function ArtistFollowButton({ artistId }: { artistId: string }) {
  const dispatch = useAppDispatch();
  const followed = useAppSelector((state) => state.follows.artistIds.includes(artistId));
  const pending = useAppSelector((state) =>
    state.follows.pendingToggles.includes(artistId),
  );
  return (
    <FollowButton
      followed={followed}
      pending={pending}
      onToggle={() => void dispatch(toggleFollow({ artistId, followed }))}
    />
  );
}
