import { UIAbility } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void {
    try {
      stage.loadContent('pages/Index').catch((error: BusinessError) => {
        hilog.error(0x0000, 'USBProbe', 'Load page failed: %{public}d', error.code);
      });
    } catch (e) {
      hilog.error(0x0000, 'USBProbe', 'Load page threw: %{public}d', (e as BusinessError).code);
    }
  }
}
