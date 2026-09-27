import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {DawnAtelier} from './showcase';
import timeline from './timeline.json';

const Root = () => <Composition id={timeline.id} component={DawnAtelier} width={timeline.width} height={timeline.height} fps={timeline.fps} durationInFrames={timeline.durationInFrames}/>;
registerRoot(Root);
