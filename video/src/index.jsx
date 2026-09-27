import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {DawnAtelier} from './showcase';

const Root = () => <Composition id="DawnAtelier" component={DawnAtelier} width={1920} height={1080} fps={30} durationInFrames={960}/>;
registerRoot(Root);
