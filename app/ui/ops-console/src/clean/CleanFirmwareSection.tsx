import { CleanIdeFirmwarePanel } from './CleanIdeFirmwarePanel';
import type { CleanGlobalStatusEvent } from './cleanAppTypes';
import type { CleanMode } from './cleanApi';

type CleanFirmwareSectionProps = {
  mode: CleanMode;
  onGlobalStatus: (evt: CleanGlobalStatusEvent) => void;
};

export function CleanFirmwareSection({
  mode,
  onGlobalStatus,
}: CleanFirmwareSectionProps): JSX.Element {
  return <CleanIdeFirmwarePanel mode={mode} onGlobalStatus={onGlobalStatus} />;
}
